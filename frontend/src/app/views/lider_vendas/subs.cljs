(ns app.views.lider-vendas.subs
  (:require [re-frame.core :as rf]))

(rf/reg-sub
 :lider-vendas/team-members
 (fn [db _]
   (get-in db [:admin :team-members])))

(rf/reg-sub
 :lider-vendas/loading?
 (fn [db _]
   (get-in db [:admin :team-loading?])))

(rf/reg-sub
 :lider-vendas/ev-detail
 (fn [db _]
   (get-in db [:admin :ev-detail])))

(rf/reg-sub
 :lider-vendas/ev-detail-loading?
 (fn [db _]
   (get-in db [:admin :ev-detail-loading?])))
