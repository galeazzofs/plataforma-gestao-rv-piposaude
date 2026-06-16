(ns app.views.revops.cn-goals
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.views.cn.calc :as calc]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn- fmt-int [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (.toLocaleString (js/Math.round n) "pt-BR")))))

(rf/reg-event-fx
 :revops/fetch-cn-goals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-goals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-goals "?month=" month "&year=" year)
           :on-success [:revops/cn-goals-loaded]
           :on-failure [:revops/cn-goals-error]}}))

(rf/reg-event-db
 :revops/cn-goals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-goals] (:data response))
       (assoc-in [:admin :cn-goals-loading?] false))))

(rf/reg-event-db
 :revops/cn-goals-error
 (fn [db _] (assoc-in db [:admin :cn-goals-loading?] false)))

(rf/reg-event-fx
 :revops/save-cn-goals
 (fn [_ [_ payload]]
   {:http {:method     :put
           :url        ep/cn-goals
           :body       payload
           :on-success [:revops/cn-goals-saved (:month payload) (:year payload)]
           :on-failure [:revops/cn-goals-error]}}))

(rf/reg-event-fx
 :revops/cn-goals-saved
 (fn [_ [_ month year _response]]
   {:dispatch [:revops/fetch-cn-goals month year]}))

(rf/reg-sub :revops/cn-goals (fn [db _] (get-in db [:admin :cn-goals] [])))
(rf/reg-sub :revops/cn-goals-loading? (fn [db _] (get-in db [:admin :cn-goals-loading?])))

(defn page []
  (let [filter-state (r/atom {:month "4" :year "2026"})
        edits        (r/atom {})
        select-period (fn [k v]
                        (swap! filter-state assoc k v)
                        (reset! edits {})
                        (rf/dispatch [:revops/fetch-cn-goals
                                      (:month @filter-state) (:year @filter-state)]))]
    (rf/dispatch [:revops/fetch-cn-goals (:month @filter-state) (:year @filter-state)])
    (fn []
      (let [goals    @(rf/subscribe [:revops/cn-goals])
            loading? @(rf/subscribe [:revops/cn-goals-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            field-val (fn [row k]
                        (let [edited (get-in @edits [(:cn_id row) k] ::none)]
                          (if (= edited ::none)
                            (or (get row k) "")
                            edited)))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "metas CN"]
          :title "Metas Mensais · CN"
          :subtitle "Defina a meta SAO — a meta de vidas é calculada pelo porte"
          :header-actions
          [[:div.search
            [layout/icon "calendar" {:width 14 :height 14}]
            [:span (str (:month @filter-state) "/" (:year @filter-state))]]
           [:button.btn.btn-primary
            {:disabled (empty? @edits)
             :on-click (fn []
                         (let [items (mapv (fn [[cn-id vals]]
                                             (let [row (first (filter #(= (:cn_id %) cn-id) goals))]
                                               ;; Only SAO is sent — the backend derives the
                                               ;; lives target from the CN porte (SAO × factor).
                                               {:cn_id      cn-id
                                                :sao_target (or (:sao_target vals) (:sao_target row) "0")
                                                :negocios_cadencia_meta (or (:negocios_cadencia_meta vals) (:negocios_cadencia_meta row) "0")
                                                :emails_meta (or (:emails_meta vals) (:emails_meta row) "0")
                                                :qualis_agendadas_meta (or (:qualis_agendadas_meta vals) (:qualis_agendadas_meta row) "0")}))
                                           @edits)]
                           (rf/dispatch [:revops/save-cn-goals
                                         {:month (:month @filter-state)
                                          :year  (:year @filter-state)
                                          :items items}])
                           (reset! edits {})))}
            [layout/icon "check" {:width 14 :height 14}] "Salvar metas"]]}

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [m (range 1 13)]
            ^{:key m}
            [:button {:type "button"
                      :class (str "chip" (when (= (str m) (:month @filter-state)) " active"))
                      :aria-pressed (str (= (str m) (:month @filter-state)))
                      :aria-label (str "Mês " m)
                      :on-click #(select-period :month (str m))}
             (str m)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y ["2025" "2026"]]
            ^{:key y}
            [:button {:type "button"
                      :class (str "chip" (when (= y (:year @filter-state)) " active"))
                      :aria-pressed (str (= y (:year @filter-state)))
                      :on-click #(select-period :year y)}
             y])]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "CN"]
             [:th.right "Meta SAO (R$)"]
             [:th.right "Meta Vidas (auto)"]
             [:th.right "Cadência (rampagem)"]]]
           [:tbody
            (cond
              (and loading? (empty? goals))
              [:tr [:td {:col-span 4 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? goals)
              [:tr [:td {:col-span 4 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhum CN ativo encontrado"]]

              :else
              (for [row goals]
                ^{:key (:cn_id row)}
                [:tr
                 [:td.name (or (:cn_name row) (str "CN " (:cn_id row)))]
                 [:td.right
                  [:input.field-input
                   {:type "number" :inputMode "decimal"
                    :style {:width "180px" :text-align "right" :padding "6px 10px"}
                    :placeholder "0"
                    :value (field-val row :sao_target)
                    :on-change #(swap! edits assoc-in [(:cn_id row) :sao_target] (.. % -target -value))}]]
                 [:td.right.num
                  (let [sao   (calc/->num (field-val row :sao_target))
                        vidas (calc/vidas-meta-from-sao sao (:porte row))]
                    (cond
                      (nil? (:porte row))     [:span.muted "defina o porte"]
                      (and vidas (pos? vidas)) (fmt-int vidas)
                      :else                    "·"))]
                 [:td.right
                  (if (:em_rampagem row)
                    (let [sao (calc/->num (field-val row :sao_target))]
                      (if (and sao (pos? sao))
                        [:input.field-input
                         {:type "number" :inputMode "decimal"
                          :placeholder "Qualis (meta)"
                          :style {:width "130px" :text-align "right" :padding "6px 10px"}
                          :value (field-val row :qualis_agendadas_meta)
                          :on-change #(swap! edits assoc-in [(:cn_id row) :qualis_agendadas_meta] (.. % -target -value))}]
                        [:div {:style {:display "flex" :gap "6px" :justify-content "flex-end"}}
                         [:input.field-input
                          {:type "number" :inputMode "decimal"
                           :placeholder "Negócios (meta)"
                           :style {:width "130px" :text-align "right" :padding "6px 10px"}
                           :value (field-val row :negocios_cadencia_meta)
                           :on-change #(swap! edits assoc-in [(:cn_id row) :negocios_cadencia_meta] (.. % -target -value))}]
                         [:input.field-input
                          {:type "number" :inputMode "decimal"
                           :placeholder "Emails (meta)"
                           :style {:width "130px" :text-align "right" :padding "6px 10px"}
                           :value (field-val row :emails_meta)
                           :on-change #(swap! edits assoc-in [(:cn_id row) :emails_meta] (.. % -target -value))}]]))
                    [:span.muted "—"])]]))]]]]))))
