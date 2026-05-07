(ns app.views.finance.subs
  (:require [re-frame.core :as rf]))

(rf/reg-sub
 :finance/dashboard
 (fn [db _]
   (get-in db [:finance :dashboard])))

(rf/reg-sub
 :finance/loading?
 (fn [db _]
   (get-in db [:finance :loading?])))

(rf/reg-sub
 :finance/dashboard-error
 (fn [db _]
   (get-in db [:finance :dashboard-error])))

(rf/reg-sub
 :finance/approval-items
 (fn [db _]
   (get-in db [:finance :approval-items])))

(rf/reg-sub
 :finance/approval-loading?
 (fn [db _]
   (get-in db [:finance :approval-loading?])))

(rf/reg-sub
 :finance/period
 (fn [db _]
   (or (get-in db [:finance :period])
       {:year :all :quarter :all})))
