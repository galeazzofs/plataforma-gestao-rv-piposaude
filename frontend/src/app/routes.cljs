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

    ;; Gerente
    ["/gerente"
     ["/dashboard"    {:name :gerente/dashboard  :role #{:GERENTE :ADMIN}}]
     ["/ev/:ev-id"    {:name :gerente/ev-detail  :role #{:GERENTE :ADMIN}}]]

    ;; Finance
    ["/finance"
     ["/dashboard" {:name :finance/dashboard :role #{:FINANCE :ADMIN}}]
     ["/approval"  {:name :finance/approval  :role #{:FINANCE :ADMIN}}]]

    ;; RevOps (Admin)
    ["/admin"
     ["/dashboard"          {:name :revops/dashboard        :role #{:ADMIN}}]
     ["/policies"           {:name :revops/policies        :role #{:ADMIN}}]
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

;; Re-frame events for routing
(rf/reg-event-db
 :route/changed
 (fn [db [_ match]]
   (assoc db :current-route match)))

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

;; Navigate event — dispatched from views as [:navigate! :route] or [:navigate! [:route params]]
(rf/reg-event-fx
 :navigate!
 (fn [_ [_ route-or-pair]]
   {:navigate! route-or-pair}))
