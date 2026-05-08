(ns app.views.lider-vendas.events
  (:require [re-frame.core :as rf]))

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
   (-> db
       (assoc-in [:admin :team-members]  (get-in response [:data :members]))
       (assoc-in [:admin :team-loading?] false))))

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
