(ns app.routes
  (:require [reitit.frontend :as rf-router]
            [reitit.frontend.easy :as rfe]
            [re-frame.core :as rf]))

(def routes
  (rf-router/router
   [["/" {:name :home}]
    ["/login" {:name :login}]
    ["/no-role" {:name :no-role}]

    ;; EV / CN
    ["/ev"
     ["/dashboard"  {:name :ev/dashboard  :role #{:EV :CN :ADMIN}}]
     ["/history"    {:name :ev/history    :role #{:EV :CN :ADMIN}}]
     ["/validation" {:name :ev/validation :role #{:EV :CN :ADMIN}}]]

    ;; CN
    ["/cn"
     ["/simulator"  {:name :cn/simulator  :role #{:CN :ADMIN}}]
     ["/dashboard"  {:name :cn/dashboard  :role #{:CN :ADMIN}}]]

    ;; Líder de Vendas
    ["/lider-vendas"
     ["/dashboard"    {:name :lider-vendas/dashboard  :role #{:LIDER_VENDAS :ADMIN}}]
     ["/ev/:ev-id"    {:name :lider-vendas/ev-detail  :role #{:LIDER_VENDAS :ADMIN}}]]

    ;; Finance
    ["/finance"
     ["/dashboard" {:name :finance/dashboard :role #{:FINANCE :ADMIN}}]
     ["/approval"  {:name :finance/approval  :role #{:FINANCE :ADMIN}}]]

    ;; RevOps (Admin)
    ["/admin"
     ["/dashboard"          {:name :revops/dashboard        :role #{:ADMIN}}]
     ["/policies"           {:name :revops/policies        :role #{:ADMIN :FINANCE}}]
     ["/users"              {:name :revops/users            :role #{:ADMIN}}]
     ["/teams"              {:name :revops/teams            :role #{:ADMIN}}]
     ["/goals"              {:name :revops/goals            :role #{:ADMIN}}]
     ["/achievements"       {:name :revops/achievements     :role #{:ADMIN}}]
     ["/commission-table"   {:name :revops/commission-table :role #{:ADMIN}}]
     ["/financial"          {:name :revops/financial        :role #{:ADMIN}}]
     ["/appraisal"          {:name :revops/appraisal        :role #{:ADMIN}}]
     ["/appraisal/:id/review" {:name :revops/appraisal-review :role #{:ADMIN}}]
     ["/cn-goals"           {:name :revops/cn-goals        :role #{:ADMIN}}]
     ["/cn-appraisal"       {:name :revops/cn-appraisal    :role #{:ADMIN}}]
     ["/ev-bonus"           {:name :revops/ev-bonus        :role #{:ADMIN}}]
     ["/leadership"         {:name :revops/leadership      :role #{:ADMIN}}]
     ["/contestations"      {:name :revops/contestations    :role #{:ADMIN}}]
     ["/sync"               {:name :revops/sync-status      :role #{:ADMIN}}]
     ["/audit"              {:name :revops/audit-log        :role #{:ADMIN}}]
     ["/settings"           {:name :revops/settings         :role #{:ADMIN}}]]]))

(defn init-routing! []
  (rfe/start!
   routes
   (fn [match]
     (when match
       (rf/dispatch [:route/changed match])))
   {:use-fragment false}))

;; Landing route per role — also used by :auth/login-success.
(defn role->landing [role]
  (case role
    "ADMIN"   :revops/dashboard
    "FINANCE" :finance/dashboard
    "LIDER_VENDAS" :lider-vendas/dashboard
    "EV"      :ev/dashboard
    "CN"      :ev/dashboard
    :no-role))

;; Re-frame events for routing.
;; When an authenticated user lands on :home or :login (e.g. fresh page load
;; on `/`, manual nav to `/login`, browser back), redirect to their landing
;; instead of falling through to the 404 view.
(rf/reg-event-fx
 :route/changed
 (fn [{:keys [db]} [_ match]]
   (let [route-name (get-in match [:data :name])
         logged-in? (some? (get-in db [:auth :user]))]
     (cond-> {:db (assoc db :current-route match)}
       (and logged-in? (#{:home :login} route-name))
       (assoc :navigate! (role->landing (get-in db [:auth :user :role])))))))

(rf/reg-sub
 :current-route
 (fn [db _] (:current-route db)))

(rf/reg-sub
 :current-route-name
 :<- [:current-route]
 (fn [route _]
   (get-in route [:data :name])))

;; Navigate effect — pushes state into browser history via reitit
;; Accepts either a route-name keyword or a [route-name params] vector
(rf/reg-fx
 :navigate!
 (fn [route-or-pair]
   (if (vector? route-or-pair)
     (let [[route-name params] route-or-pair]
       (if params
         (rfe/push-state route-name params)
         (rfe/push-state route-name)))
     (rfe/push-state route-or-pair))))

