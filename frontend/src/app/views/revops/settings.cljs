(ns app.views.revops.settings
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn toggle-field [{:keys [label description value on-change]}]
  [:div {:style {:display "flex" :justify-content "space-between" :align-items "flex-start"
                 :padding "16px 0" :border-bottom (str "1px solid " t/bg-subtle)}}
   [:div
    [:div {:style {:font-size (:sm t/font-sizes) :font-weight (:medium t/font-weights)}} label]
    (when description
      [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :margin-top "2px"}} description])]
   [:label {:style {:position "relative" :display "inline-block" :width "44px" :height "24px" :cursor "pointer"}}
    [:input {:type      "checkbox"
             :checked   (boolean value)
             :style     {:opacity "0" :width "0" :height "0"}
             :on-change #(on-change (.. % -target -checked))}]
    [:span {:style {:position "absolute" :cursor "pointer" :inset "0"
                    :background (if value t/color-primary t/border-default)
                    :border-radius (:full t/border-radius)
                    :transition t/transition-fast}}
     [:span {:style {:position "absolute" :content "''"
                     :height "18px" :width "18px"
                     :left (if value "23px" "3px")
                     :bottom "3px"
                     :background t/color-white
                     :border-radius (:full t/border-radius)
                     :transition t/transition-fast}}]]]])

(defn- map->rows [m]
  (mapv (fn [[k v]] {:owner-id (if (keyword? k) (name k) (str k))
                     :ev-email (str v)})
        (or m {})))

(defn- rows->map [rows]
  (into {} (keep (fn [{:keys [owner-id ev-email]}]
                   (when (and (seq owner-id) (seq ev-email))
                     [owner-id ev-email]))
                 rows)))

(defn owner-map-editor [rows ev-users on-change]
  [:div
   (for [[idx row] (map-indexed vector @rows)]
     ^{:key idx}
     [:div {:style {:display "flex" :gap "8px" :align-items "flex-end" :margin-bottom "8px"}}
      [inputs/input
       {:label (when (zero? idx) "HubSpot Owner ID")
        :placeholder "ex: 158520480"
        :value (:owner-id row)
        :on-change #(do (swap! rows assoc-in [idx :owner-id] %)
                        (on-change))}]
      [inputs/select
       {:label (when (zero? idx) "EV na Plataforma")
        :value (:ev-email row)
        :options (into [{:value "" :label "— Selecionar EV —"}]
                       (map (fn [u] {:value (:email u) :label (:name u)}) ev-users))
        :on-change #(do (swap! rows assoc-in [idx :ev-email] %)
                        (on-change))}]
      [btn/button {:variant :ghost :size :sm
                   :on-click #(do (swap! rows (fn [r] (vec (keep-indexed (fn [i v] (when (not= i idx) v)) r))))
                                  (on-change))}
       "✕"]])
   [btn/button {:variant :secondary :size :sm
                :on-click #(do (swap! rows conj {:owner-id "" :ev-email ""})
                               (on-change))}
    "+ Adicionar mapeamento"]])

(defn settings-page []
  (r/with-let [local-settings (r/atom nil)
               owner-map-rows (r/atom [])
               settings-sub   (rf/subscribe [:revops/settings])
               ;; r/track! runs the body whenever the sub changes, OUTSIDE the
               ;; render cycle. Avoids the Reagent anti-pattern of calling
               ;; reset! during render (which triggers re-render of subscribers).
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
          route    @(rf/subscribe [:current-route-name])]

      (let [form (or @local-settings settings {})]

        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Configurações"
          :subtitle      "Parâmetros globais da plataforma"
          :header-actions
          [btn/button {:variant  :primary
                       :loading  loading?
                       :on-click #(rf/dispatch [:revops/save-settings
                                                (assoc @local-settings
                                                       :hubspot_owner_map (rows->map @owner-map-rows))])}
           "Salvar Configurações"]}

         [cards/card {}
          (if (and loading? (nil? settings))
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Carregando..."]
            [:div {:style {:display "flex" :flex-direction "column"}}

             ;; Deadlines section
             [:h4 {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights)
                            :margin "0 0 16px"}} "Prazos"]
             [:div {:style {:display "grid" :grid-template-columns "1fr 1fr" :gap "16px" :margin-bottom "32px"}}
              [inputs/input
               {:label     "Prazo de Validação (dias)"
                :type      "number"
                :value     (str (or (:validation_deadline_days form) ""))
                :on-change #(swap! local-settings assoc :validation_deadline_days (js/parseInt %))}]
              [inputs/input
               {:label     "Intervalo de Sync (horas)"
                :type      "number"
                :value     (str (or (:sync_interval_hours form) ""))
                :on-change #(swap! local-settings assoc :sync_interval_hours (js/parseInt %))}]]

             ;; Notifications section
             [:h4 {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights)
                            :margin "0 0 8px"}} "Notificações"]
             [toggle-field
              {:label       "Notificar EVs na abertura de validação"
               :description "Envia e-mail quando o período de validação iniciar"
               :value       (:notify_ev_validation_open form)
               :on-change   #(swap! local-settings assoc :notify_ev_validation_open %)}]
             [toggle-field
              {:label       "Notificar Finance na aprovação"
               :description "Envia e-mail quando uma apuração for aprovada para pagamento"
               :value       (:notify_finance_approval form)
               :on-change   #(swap! local-settings assoc :notify_finance_approval %)}]
             [toggle-field
              {:label       "Notificar RevOps em erros de sync"
               :description "Alerta quando a sincronização com HubSpot falhar"
               :value       (:notify_revops_sync_error form)
               :on-change   #(swap! local-settings assoc :notify_revops_sync_error %)}]

             ;; HubSpot Owner Mapping section
             [:h4 {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights)
                            :margin "32px 0 4px"}} "Mapeamento de Proprietários HubSpot"]
             [:p {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :margin "0 0 16px"}}
              "Use isto para mapear IDs de proprietários removidos do HubSpot aos EVs da plataforma. "
              "O ID do proprietário está visível na URL do perfil do usuário no HubSpot ou nos logs de sync."]
             [owner-map-editor owner-map-rows ev-users (fn [] nil)]])]]))))
