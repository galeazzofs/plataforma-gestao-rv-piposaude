(ns app.views.revops.leadership-appraisal
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]))

(rf/reg-event-fx
 :revops/fetch-leadership-preview
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (assoc-in db [:admin :leadership-loading?] true)
    :http {:method     :get
           :url        (str ep/leadership-preview "?quarter=" quarter "&year=" year)
           :on-success [:revops/leadership-preview-loaded]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-db
 :revops/leadership-preview-loaded
 (fn [db [_ r]] (-> db (assoc-in [:admin :leadership-preview] (:data r))
                       (assoc-in [:admin :leadership-loading?] false))))

(rf/reg-event-fx
 :revops/fetch-leadership-appraisals
 (fn [{:keys [db]} [_ quarter year]]
   {:http {:method     :get
           :url        (str ep/leadership-appraisal "?quarter=" quarter "&year=" year)
           :on-success [:revops/leadership-appraisals-loaded]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-db
 :revops/leadership-appraisals-loaded
 (fn [db [_ r]] (assoc-in db [:admin :leadership-appraisals] (:data r))))

(rf/reg-event-db :revops/leadership-error (fn [db _] (assoc-in db [:admin :leadership-loading?] false)))

(rf/reg-event-fx
 :revops/run-leadership-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/leadership-appraisal
           :body       payload
           :on-success [:revops/fetch-leadership-appraisals
                        (:quarter payload) (:year payload)]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-fx
 :revops/finalize-leadership
 (fn [_ [_ id quarter year]]
   {:http {:method     :post
           :url        (ep/leadership-finalize id)
           :body       {}
           :on-success [:revops/fetch-leadership-appraisals quarter year]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-sub :revops/leadership-preview (fn [db _] (get-in db [:admin :leadership-preview] [])))
(rf/reg-sub :revops/leadership-appraisals (fn [db _] (get-in db [:admin :leadership-appraisals] [])))
(rf/reg-sub :revops/leadership-loading? (fn [db _] (get-in db [:admin :leadership-loading?])))

(defn page []
  (let [filter-s (r/atom {:quarter "1" :year "2026"})
        inputs   (r/atom {})]
    (fn []
      (let [preview  @(rf/subscribe [:revops/leadership-preview])
            results  @(rf/subscribe [:revops/leadership-appraisals])
            loading? @(rf/subscribe [:revops/leadership-loading?])]
        [layout/page {:title "Apuração Liderança — GERENTEs"}
         [cards/card
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select {:label "Trimestre" :value (:quarter @filter-s)
                           :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                                     {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
                           :on-change #(swap! filter-s assoc :quarter %)}]
           [inputs/select {:label "Ano" :value (:year @filter-s)
                           :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
                           :on-change #(swap! filter-s assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-leadership-preview
                                                 (:quarter @filter-s) (:year @filter-s)])}
            "Carregar"]]

          (when (seq preview)
            [:div {:style {:margin-bottom "16px"}}
             [:p {:style {:font-size "13px" :font-weight "600" :margin-bottom "8px"}}
              "Preencha os valores realizados:"]
             (for [{:keys [gerente_id gerente_name meta_mrr]} preview]
               ^{:key gerente_id}
               [:div {:style {:display "flex" :gap "12px" :align-items "center"
                              :margin-bottom "8px"}}
                [:span {:style {:width "140px" :font-size "13px"}} gerente_name]
                [:span {:style {:width "120px" :font-size "12px" :color "#666"}}
                 (str "Meta MRR: R$ " meta_mrr " (auto)")]
                [inputs/text-field
                 {:label "MRR Realizado"
                  :value (get-in @inputs [gerente_id :realizado_mrr] "")
                  :on-change #(swap! inputs assoc-in [gerente_id :realizado_mrr] %)}]
                [inputs/text-field
                 {:label "Meta SQL" :type :number
                  :value (get-in @inputs [gerente_id :meta_sql] "")
                  :on-change #(swap! inputs assoc-in [gerente_id :meta_sql] %)}]
                [inputs/text-field
                 {:label "SQL Realizado" :type :number
                  :value (get-in @inputs [gerente_id :realizado_sql] "")
                  :on-change #(swap! inputs assoc-in [gerente_id :realizado_sql] %)}]])])

          (when (seq preview)
            [btn/button
             {:variant :primary
              :on-click (fn []
                          (rf/dispatch
                           [:revops/run-leadership-appraisal
                            {:quarter (:quarter @filter-s)
                             :year    (:year @filter-s)
                             :inputs  (mapv (fn [[gid vals]]
                                              (merge {:gerente_id gid} vals))
                                            @inputs)}]))}
             "Calcular Bônus"])

          (when (seq results)
            [:div {:style {:margin-top "24px"}}
             [tbl/table
              {:loading? loading?
               :columns  [{:key :gerente_id   :label "Gerente"}
                          {:key :meta_mrr     :label "Meta MRR"}
                          {:key :pct_mrr      :label "% MRR"}
                          {:key :pct_sql      :label "% SQL"}
                          {:key :multiplicador :label "Mult."}
                          {:key :bonus_amount  :label "Bônus (R$)"}
                          {:key :is_final      :label "Status"
                           :render (fn [v row]
                                     (if v
                                       [badge/badge {:variant :success} "Final"]
                                       [btn/button
                                        {:variant :primary :size :sm
                                         :on-click #(rf/dispatch
                                                     [:revops/finalize-leadership
                                                      (:id row)
                                                      (:quarter @filter-s)
                                                      (:year @filter-s)])}
                                        "Finalizar"]))}]
               :rows     results}]])]]))))
