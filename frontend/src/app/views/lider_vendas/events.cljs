(ns app.views.lider-vendas.events
  (:require [re-frame.core :as rf]
            [app.api.client :as client]
            [app.api.endpoints :as ep]))

(rf/reg-event-fx
 :lider-vendas/fetch-team
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :team-loading?] true)
    :http {:method     :get
           :url        "/lider-vendas/team"
           :on-success [:lider-vendas/team-loaded]
           :on-failure [:lider-vendas/team-error]}}))

(rf/reg-event-db
 :lider-vendas/team-loaded
 (fn [db [_ response]]
   (let [data (get-in response [:data])
         members (if (map? data) (:members data) data)]
     (-> db
         (assoc-in [:admin :team-members]  members)
         (assoc-in [:admin :team-loading?] false)))))

(rf/reg-event-db
 :lider-vendas/team-error
 (fn [db _]
   (assoc-in db [:admin :team-loading?] false)))

(rf/reg-event-fx
 :lider-vendas/fetch-ev-detail
 (fn [{:keys [db]} [_ ev-id]]
   {:db   (assoc-in db [:admin :ev-detail-loading?] true)
    :http {:method     :get
           :url        (str "/lider-vendas/ev/" ev-id)
           :on-success [:lider-vendas/ev-detail-loaded]
           :on-failure [:lider-vendas/ev-detail-error]}}))

(rf/reg-event-db
 :lider-vendas/ev-detail-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :ev-detail]         (get-in response [:data]))
       (assoc-in [:admin :ev-detail-loading?] false))))

(rf/reg-event-db
 :lider-vendas/ev-detail-error
 (fn [db _]
   (assoc-in db [:admin :ev-detail-loading?] false)))

(rf/reg-event-fx
 :lider-vendas/fetch-team-appraisal
 (fn [_ _]
   {:http {:method     :get
           :url        "/lider-vendas/appraisal"
           :on-success [:lider-vendas/team-appraisal-loaded]
           :on-failure [:lider-vendas/team-appraisal-error]}}))

(rf/reg-event-db
 :lider-vendas/team-appraisal-loaded
 (fn [db [_ response]]
   (assoc-in db [:lider-vendas :team-appraisal] (:data response))))

(rf/reg-event-db
 :lider-vendas/team-appraisal-error
 (fn [db _]
   (assoc-in db [:lider-vendas :team-appraisal] nil)))

(rf/reg-event-fx
 :lider-vendas/approve-team-appraisal
 (fn [_ [_ appraisal-id]]
   {:http {:method     :post
           :url        (str "/lider-vendas/appraisal/" appraisal-id "/approve")
           :on-success [:lider-vendas/team-appraisal-action-ok]
           :on-failure [:lider-vendas/team-appraisal-action-err]}}))

(rf/reg-event-fx
 :lider-vendas/team-appraisal-action-ok
 (fn [_ _]
   {:dispatch-n [[:lider-vendas/fetch-team-appraisal]
                 [:lider-vendas/fetch-team]
                 [:ui/show-toast {:type :success
                                  :message "Apuração aprovada e enviada para o RevOps."}]]}))

(rf/reg-event-fx
 :lider-vendas/team-appraisal-action-err
 (fn [_ [_ response]]
   (let [msg (client/error-message response "Erro ao aprovar a apuração.")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))

(rf/reg-event-fx
 :lider-vendas/fetch-appraisals
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:lider-vendas :appraisals-loading?] true)
    :http {:method     :get
           :url        ep/leadership-appraisal
           :on-success [:lider-vendas/appraisals-loaded]
           :on-failure [:lider-vendas/appraisals-error]}}))

(rf/reg-event-db
 :lider-vendas/appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:lider-vendas :appraisals] (:data response))
       (assoc-in [:lider-vendas :appraisals-loading?] false))))

(rf/reg-event-db
 :lider-vendas/appraisals-error
 (fn [db _]
   (assoc-in db [:lider-vendas :appraisals-loading?] false)))

(rf/reg-event-fx
 :lider-vendas/approve-appraisal
 (fn [_ [_ appraisal-id]]
   {:http {:method     :post
           :url        (ep/leadership-transition appraisal-id)
           :body       {:to "LIDER_REVIEW"}
           :on-success [:lider-vendas/appraisal-action-success]
           :on-failure [:lider-vendas/appraisal-action-error]}}))

(rf/reg-event-fx
 :lider-vendas/appraisal-action-success
 (fn [_ _]
   {:dispatch-n [[:lider-vendas/fetch-appraisals]
                 [:lider-vendas/fetch-team]
                 [:ui/show-toast {:type :success
                                  :message "Apuracao aprovada"}]]}))

(rf/reg-event-fx
 :lider-vendas/appraisal-action-error
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :error
                               :message "Erro ao aprovar apuracao"}]}))
