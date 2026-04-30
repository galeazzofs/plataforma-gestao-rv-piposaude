(ns app.views.revops.cn-appraisal
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :revops/fetch-cn-appraisals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-appraisals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-appraisal "?month=" month "&year=" year)
           :on-success [:revops/cn-appraisals-loaded]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-db
 :revops/cn-appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-appraisals] (:data response))
       (assoc-in [:admin :cn-appraisals-loading?] false))))

(rf/reg-event-db
 :revops/cn-appraisals-error
 (fn [db _] (assoc-in db [:admin :cn-appraisals-loading?] false)))

(rf/reg-event-fx
 :revops/run-cn-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/cn-appraisal
           :body       payload
           :on-success [:revops/cn-appraisal-done (:month payload) (:year payload)]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-fx
 :revops/cn-appraisal-done
 (fn [_ [_ month year _response]]
   {:dispatch [:revops/fetch-cn-appraisals month year]}))

(rf/reg-event-fx
 :revops/finalize-cn-appraisal
 (fn [_ [_ id month year]]
   {:http {:method     :post
           :url        (ep/cn-appraisal-finalize id)
           :body       {}
           :on-success [:revops/fetch-cn-appraisals month year]
           :on-failure [:revops/cn-appraisals-error]}}))

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub :revops/cn-appraisals (fn [db _] (get-in db [:admin :cn-appraisals] [])))
(rf/reg-sub :revops/cn-appraisals-loading? (fn [db _] (get-in db [:admin :cn-appraisals-loading?])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn page []
  (let [filter-s     (r/atom {:month "4" :year "2026"})
        form-inputs  (r/atom {})]
    (fn []
      (let [items    @(rf/subscribe [:revops/cn-appraisals])
            loading? @(rf/subscribe [:revops/cn-appraisals-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Apuração Mensal CN"}
         [cards/card {}
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select
            {:label "Mês" :value (:month @filter-s)
             :options (mapv (fn [m] {:value (str m) :label (str m)}) (range 1 13))
             :on-change #(swap! filter-s assoc :month %)}]
           [inputs/select
            {:label "Ano" :value (:year @filter-s)
             :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
             :on-change #(swap! filter-s assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-cn-appraisals
                                                 (:month @filter-s) (:year @filter-s)])}
            "Buscar"]]

          [:div {:style {:margin-bottom "16px"}}
           [:p {:style {:font-size "13px" :color t/text-secondary :margin-bottom "8px"}}
            "Preencha os valores realizados e clique em Rodar Apuração."]]

          [btn/button
           {:variant  :primary
            :on-click (fn []
                        (rf/dispatch [:revops/run-cn-appraisal
                                      {:month  (:month @filter-s)
                                       :year   (:year @filter-s)
                                       :inputs (mapv (fn [[cn-id vals]]
                                                       (merge {:cn_id cn-id} vals))
                                                     @form-inputs)}]))}
           "Rodar Apuração"]

          (if loading?
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}}
             "Carregando..."]
            [tbl/data-table
             {:columns  [{:key :cn_name         :label "CN"}
                         {:key :score_final     :label "Score"}
                         {:key :multiplicador   :label "Mult."}
                         {:key :commission_amount :label "Comissão (R$)"}
                         {:key :is_final        :label "Status"
                          :render (fn [row]
                                    (if (:is_final row)
                                      [badge/badge {:variant :success} "Final"]
                                      [btn/button {:variant :primary :size :sm
                                                   :on-click #(rf/dispatch
                                                                [:revops/finalize-cn-appraisal
                                                                 (:id row)
                                                                 (:month @filter-s)
                                                                 (:year @filter-s)])}
                                       "Finalizar"]))}]
              :rows     items}])]]))))
