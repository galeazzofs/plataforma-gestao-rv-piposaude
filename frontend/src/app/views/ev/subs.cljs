(ns app.views.ev.subs
  (:require [re-frame.core :as rf]))

(rf/reg-sub
 :ev/summary
 (fn [db _]
   (get-in db [:commissions :summary])))

(rf/reg-sub
 :ev/policies
 (fn [db _]
   (get-in db [:policies :items])))

(rf/reg-sub
 :ev/policies-meta
 (fn [db _]
   (get-in db [:policies :meta])))

(rf/reg-sub
 :ev/policies-loading?
 (fn [db _]
   (get-in db [:policies :loading?])))

(rf/reg-sub
 :ev/projection
 (fn [db _]
   (get-in db [:commissions :projection])))

(rf/reg-sub
 :ev/validations
 (fn [db _]
   (get-in db [:validations :items])))

(rf/reg-sub
 :ev/loading?
 (fn [db _]
   (get-in db [:commissions :loading?])))
