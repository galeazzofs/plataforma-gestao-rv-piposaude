(ns app.views.revops.cn-goals
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.auth.subs]))

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
        edits        (r/atom {})]
    (fn []
      (let [goals    @(rf/subscribe [:revops/cn-goals])
            loading? @(rf/subscribe [:revops/cn-goals-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "metas CN"]
          :title "Metas Mensais · CN"
          :subtitle "Defina SAO e vidas mensais por consultor"
          :header-actions
          [[:div.search
            [layout/icon "calendar" {:width 14 :height 14}]
            [:span (str (:month @filter-state) "/" (:year @filter-state))]]
           [:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/fetch-cn-goals
                                      (:month @filter-state) (:year @filter-state)])}
            "Buscar"]
           [:button.btn.btn-primary
            {:on-click (fn []
                         (let [items (mapv (fn [[cn-id vals]] (merge {:cn_id cn-id} vals))
                                            @edits)]
                           (rf/dispatch [:revops/save-cn-goals
                                         {:month (:month @filter-state)
                                          :year  (:year @filter-state)
                                          :items items}])))}
            [layout/icon "check" {:width 14 :height 14}] "Salvar metas"]]}

         [:div.filter-row
          (for [m (range 1 13)]
            ^{:key m}
            [:div {:class (str "chip" (when (= (str m) (:month @filter-state)) " active"))
                   :on-click #(swap! filter-state assoc :month (str m))}
             (str m)])
          [:div {:style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y ["2025" "2026"]]
            ^{:key y}
            [:div {:class (str "chip" (when (= y (:year @filter-state)) " active"))
                   :on-click #(swap! filter-state assoc :year y)}
             y])]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "CN"]
             [:th.right "Meta SAO (R$)"]
             [:th.right "Meta Vidas"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 3 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? goals)
              [:tr [:td {:col-span 3 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma meta configurada · clique em Buscar"]]

              :else
              (for [row goals]
                ^{:key (:cn_id row)}
                [:tr
                 [:td.name (or (:cn_name row) (str "CN " (:cn_id row)))]
                 [:td.right
                  [:input.field-input
                   {:style {:width "180px" :text-align "right" :padding "6px 10px"}
                    :value (get-in @edits [(:cn_id row) :sao_target] (str (:sao_target row)))
                    :on-change #(swap! edits assoc-in [(:cn_id row) :sao_target] (.. % -target -value))}]]
                 [:td.right
                  [:input.field-input
                   {:style {:width "140px" :text-align "right" :padding "6px 10px"}
                    :value (get-in @edits [(:cn_id row) :vidas_target] (str (:vidas_target row)))
                    :on-change #(swap! edits assoc-in [(:cn_id row) :vidas_target] (.. % -target -value))}]]]))]]]]))))
