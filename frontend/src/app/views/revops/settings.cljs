(ns app.views.revops.settings
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.auth.subs]))

;; Settings — design styling: stacked cards with toggles, fields, owner mapper.

(defn- toggle-field [{:keys [label description value on-change]}]
  (let [label-id (str "tog-" (gensym))]
    [:div {:style {:display "flex" :justify-content "space-between" :align-items "flex-start"
                   :padding "16px 0" :border-bottom "1px solid var(--border-subtle)" :gap "16px"}}
     [:div {:style {:flex 1}}
      [:label {:id label-id
               :style {:font-family "var(--font-ui)" :font-size "13px" :font-weight 600
                       :color "var(--fg-1)" :display "block" :cursor "pointer"}
               :on-click #(when on-change (on-change (not value)))}
       label]
      (when description
        [:div {:style {:font-size "12px" :color "var(--fg-3)" :margin-top "2px"}} description])]
     [:button {:type "button"
               :class (str "tog" (when value " on"))
               :role "switch"
               :aria-checked (str (boolean value))
               :aria-labelledby label-id
               :on-click #(when on-change (on-change (not value)))}]]))

(defn- map->rows [m]
  (mapv (fn [[k v]] {:owner-id (if (keyword? k) (name k) (str k))
                     :ev-email (str v)})
        (or m {})))

(defn- rows->map [rows]
  (into {} (keep (fn [{:keys [owner-id ev-email]}]
                   (when (and (seq owner-id) (seq ev-email))
                     [owner-id ev-email]))
                 rows)))

(defn- owner-map-editor [rows ev-users]
  [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
   (for [[idx row] (map-indexed vector @rows)]
     ^{:key idx}
     [:div {:style {:display "flex" :gap "8px" :align-items "flex-end"}}
      [:div {:style {:flex 1}}
       [inputs/input
        {:label (when (zero? idx) "HubSpot Owner ID")
         :placeholder "ex: 158520480"
         :value (:owner-id row)
         :on-change #(swap! rows assoc-in [idx :owner-id] %)}]]
      [:div {:style {:flex 2}}
       [inputs/select
        {:label (when (zero? idx) "EV na Plataforma")
         :value (:ev-email row)
         :options (into [{:value "" :label "Selecionar EV"}]
                        (map (fn [u] {:value (:email u) :label (:name u)}) ev-users))
         :on-change #(swap! rows assoc-in [idx :ev-email] %)}]]
      [:button.btn.btn-ghost.btn-sm
       {:on-click #(swap! rows (fn [r] (vec (keep-indexed (fn [i v] (when (not= i idx) v)) r))))}
       "✕"]])
   [:button.btn.btn-secondary.btn-sm
    {:style {:align-self "flex-start"}
     :on-click #(swap! rows conj {:owner-id "" :ev-email ""})}
    [layout/icon "plus" {:width 12 :height 12}] "Adicionar mapeamento"]])

(defn settings-page []
  (r/with-let [local-settings (r/atom nil)
               owner-map-rows (r/atom [])
               settings-sub   (rf/subscribe [:revops/settings])
               init-track     (r/track!
                                (fn []
                                  (let [s @settings-sub]
                                    (when (and s (nil? @local-settings))
                                      (reset! local-settings s)
                                      (reset! owner-map-rows
                                              (map->rows (:hubspot_owner_map s)))))))
               _              (do (rf/dispatch [:revops/fetch-settings])
                                  (rf/dispatch [:revops/fetch-users]))]
    (let [settings @settings-sub
          loading? @(rf/subscribe [:revops/settings-loading?])
          ev-users @(rf/subscribe [:revops/ev-users])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          form     (or @local-settings settings {})]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "configuração" "settings"]
        :title "Configurações"
        :subtitle "Parâmetros globais da plataforma"
        :header-actions
        [[:button.btn.btn-primary
          {:disabled loading?
           :on-click #(rf/dispatch [:revops/save-settings
                                    (assoc @local-settings
                                           :hubspot_owner_map (rows->map @owner-map-rows))])}
          [layout/icon "check" {:width 14 :height 14}]
          (if loading? "Salvando…" "Salvar configurações")]]}

       (if (and loading? (nil? settings))
         [:div.card [:div {:style {:padding "48px" :text-align "center" :color "var(--fg-3)"}} "Carregando…"]]
         [:<>
          ;; Prazos
          [:div.card
           [:div.card-head
            [:div [:h3 "Prazos"] [:div.card-sub "Janelas de validação e sincronização"]]]
           [:div.form-grid
            [inputs/input
             {:label "Prazo de Validação (dias)" :type "number"
              :value (str (or (:validation_deadline_days form) ""))
              :on-change #(swap! local-settings assoc :validation_deadline_days (js/parseInt %))}]
            [inputs/input
             {:label "Intervalo de Sync (horas)" :type "number"
              :value (str (or (:sync_interval_hours form) ""))
              :on-change #(swap! local-settings assoc :sync_interval_hours (js/parseInt %))}]]]

          ;; Notificações
          [:div.card
           [:div.card-head
            [:div [:h3 "Notificações"] [:div.card-sub "E-mails automáticos por evento"]]]
           [:div
            [toggle-field
             {:label "Notificar EVs na abertura de validação"
              :description "Envia e-mail quando o período de validação iniciar"
              :value (:notify_ev_validation_open form)
              :on-change #(swap! local-settings assoc :notify_ev_validation_open %)}]
            [toggle-field
             {:label "Notificar Finance na aprovação"
              :description "Envia e-mail quando uma apuração for aprovada para pagamento"
              :value (:notify_finance_approval form)
              :on-change #(swap! local-settings assoc :notify_finance_approval %)}]
            [toggle-field
             {:label "Notificar RevOps em erros de sync"
              :description "Alerta quando a sincronização com HubSpot falhar"
              :value (:notify_revops_sync_error form)
              :on-change #(swap! local-settings assoc :notify_revops_sync_error %)}]]]

          ;; Comissão CN — Rampagem
          [:div.card
           [:div.card-head
            [:div [:h3 "Comissão CN · Rampagem"]
             [:div.card-sub "Parâmetros do cálculo de rampagem"]]]
           [:div.form-grid
            [inputs/input
             {:label "Bônus por SAO fora da meta (R$)" :type "number"
              :placeholder "300"
              :value (str (or (:cn_rampagem_bonus_sao form) ""))
              :on-change #(swap! local-settings assoc :cn_rampagem_bonus_sao %)}]]]

          ;; HubSpot Owner Mapping
          [:div.card
           [:div.card-head
            [:div [:h3 "Mapeamento de Proprietários HubSpot"]
             [:div.card-sub
              "Use isto para mapear IDs de proprietários removidos do HubSpot aos EVs da plataforma"]]]
           [owner-map-editor owner-map-rows ev-users]]])])))
