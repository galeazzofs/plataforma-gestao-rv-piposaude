(ns app.views.gerente.subs
  (:require [re-frame.core :as rf]))

(rf/reg-sub
 :gerente/team-members
 (fn [db _]
   (get-in db [:admin :team-members])))

(rf/reg-sub
 :gerente/loading?
 (fn [db _]
   (get-in db [:admin :team-loading?])))

(rf/reg-sub
 :gerente/ev-detail
 (fn [db _]
   (get-in db [:admin :ev-detail])))

(rf/reg-sub
 :gerente/ev-detail-loading?
 (fn [db _]
   (get-in db [:admin :ev-detail-loading?])))
