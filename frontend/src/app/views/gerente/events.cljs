(ns app.views.gerente.events
  (:require [re-frame.core :as rf]))

(rf/reg-event-fx
 :gerente/fetch-team
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :team-loading?] true)
    :http {:method     :get
           :url        "/gerente/team"
           :on-success [:gerente/team-loaded]
           :on-failure [:gerente/team-error]}}))

(rf/reg-event-db
 :gerente/team-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :team-members]  (get-in response [:data :members]))
       (assoc-in [:admin :team-loading?] false))))

(rf/reg-event-db
 :gerente/team-error
 (fn [db _]
   (assoc-in db [:admin :team-loading?] false)))

(rf/reg-event-fx
 :gerente/fetch-ev-detail
 (fn [{:keys [db]} [_ ev-id]]
   {:db   (assoc-in db [:admin :ev-detail-loading?] true)
    :http {:method     :get
           :url        (str "/gerente/ev/" ev-id)
           :on-success [:gerente/ev-detail-loaded]
           :on-failure [:gerente/ev-detail-error]}}))

(rf/reg-event-db
 :gerente/ev-detail-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :ev-detail]         (get-in response [:data]))
       (assoc-in [:admin :ev-detail-loading?] false))))

(rf/reg-event-db
 :gerente/ev-detail-error
 (fn [db _]
   (assoc-in db [:admin :ev-detail-loading?] false)))
