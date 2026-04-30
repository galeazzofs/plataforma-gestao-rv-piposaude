(ns app.views.revops.ev-bonus
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(rf/reg-event-fx
 :revops/fetch-ev-bonus
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (assoc-in db [:admin :ev-bonus-loading?] true)
    :http {:method     :get
           :url        (str ep/ev-bonus "?quarter=" quarter "&year=" year)
           :on-success [:revops/ev-bonus-loaded]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-event-db
 :revops/ev-bonus-loaded
 (fn [db [_ r]] (-> db (assoc-in [:admin :ev-bonus] (:data r))
                       (assoc-in [:admin :ev-bonus-loading?] false))))

(rf/reg-event-db :revops/ev-bonus-error (fn [db _] (assoc-in db [:admin :ev-bonus-loading?] false)))

(rf/reg-event-fx
 :revops/run-ev-bonus
 (fn [_ [_ quarter year]]
   {:http {:method     :post
           :url        ep/ev-bonus
           :body       {:quarter quarter :year year}
           :on-success [:revops/fetch-ev-bonus quarter year]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-sub :revops/ev-bonus (fn [db _] (get-in db [:admin :ev-bonus] [])))
(rf/reg-sub :revops/ev-bonus-loading? (fn [db _] (get-in db [:admin :ev-bonus-loading?])))

(defn page []
  (let [filter-s (r/atom {:quarter "1" :year "2026"})]
    (fn []
      (let [items    @(rf/subscribe [:revops/ev-bonus])
            loading? @(rf/subscribe [:revops/ev-bonus-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Bônus MRR Trimestral — EVs"}
         [cards/card {}
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select {:label "Trimestre" :value (:quarter @filter-s)
                           :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                                     {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
                           :on-change #(swap! filter-s assoc :quarter %)}]
           [inputs/select {:label "Ano" :value (:year @filter-s)
                           :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
                           :on-change #(swap! filter-s assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-ev-bonus
                                                 (:quarter @filter-s) (:year @filter-s)])}
            "Buscar"]
           [btn/button {:variant :primary
                        :on-click #(rf/dispatch [:revops/run-ev-bonus
                                                 (:quarter @filter-s) (:year @filter-s)])}
            "Calcular Bônus"]]
          (if loading?
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}}
             "Carregando..."]
            [tbl/data-table
             {:columns  [{:key :ev_id              :label "EV"}
                         {:key :achievement_pct     :label "% Atingimento"}
                         {:key :salario_base_snapshot :label "Salário Base"}
                         {:key :bonus_amount         :label "Bônus (R$)"}]
              :rows     items}])]]))))
