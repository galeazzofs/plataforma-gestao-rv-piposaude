(ns app.routes
  (:require [reitit.frontend :as rf-router]
            [reitit.frontend.easy :as rfe]
            [re-frame.core :as rf]))

(def routes
  (rf-router/router
   [["/" {:name :home}]
    ["/login" {:name :login}]
    ["/no-role" {:name :no-role}]

    ;; EV
    ["/ev"
     ["/dashboard"  {:name :ev/dashboard  :role #{:EV :ADMIN}}]
     ["/history"    {:name :ev/history    :role #{:EV :ADMIN}}]
     ["/validation" {:name :ev/validation :role #{:EV :ADMIN}}]]

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
     ["/appraisal-preview"  {:name :revops/appraisal-preview :role #{:ADMIN}}]
     ["/appraisal/:id/review" {:name :revops/appraisal-review :role #{:ADMIN}}]
     ["/monthly-cycle"      {:name :revops/monthly-cycle    :role #{:ADMIN}}]
     ["/cn-goals"           {:name :revops/cn-goals        :role #{:ADMIN}}]
     ["/cn-appraisal"       {:name :revops/cn-appraisal    :role #{:ADMIN}}]
     ["/ev-bonus"           {:name :revops/ev-bonus        :role #{:ADMIN}}]
     ["/cn-quarterly-bonus" {:name :revops/cn-quarterly-bonus :role #{:ADMIN}}]
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
    "CN"      :cn/dashboard
    :no-role))

(defn route-allowed?
  "True when `user-role` (a string like \"EV\") is allowed on a route whose
   `route-roles` metadata is a set of keywords like `#{:EV :ADMIN}`. Routes
   with no `:role` metadata are public — anyone may visit them."
  [route-roles user-role]
  (or (nil? route-roles)
      (and (some? user-role)
           (contains? route-roles (keyword user-role)))))

(defn handle-route-changed
  "Pure handler for `:route/changed`. Returns the re-frame effect map.

   Two redirect cases for logged-in users:
   1. Landing on :home or :login → bounce to their role's landing page.
   2. Hitting a role-gated route they're not in → bounce, and DO NOT commit
      the new route to :current-route. Keeping :current-route on the previous
      (valid) page prevents the view from flashing the unauthorized page in
      the frame between dispatch and the redirect landing."
  [db match]
  (let [route-name  (get-in match [:data :name])
        route-roles (get-in match [:data :role])
        user-role   (get-in db [:auth :user :role])
        logged-in?  (some? (get-in db [:auth :user]))]
    (cond
      (and logged-in? (#{:home :login} route-name))
      {:db        (assoc db :current-route match)
       :navigate! (role->landing user-role)}

      (and logged-in? (not (route-allowed? route-roles user-role)))
      {:navigate! (role->landing user-role)}

      :else
      {:db (assoc db :current-route match)})))

(rf/reg-event-fx
 :route/changed
 (fn [{:keys [db]} [_ match]]
   (handle-route-changed db match)))

(rf/reg-sub
 :current-route
 (fn [db _] (:current-route db)))

(rf/reg-sub
 :current-route-name
 :<- [:current-route]
 (fn [route _]
   (get-in route [:data :name])))

;; Navigate effect — pushes state into browser history via reitit
;; Accepts a route-name keyword, [route-name params] or
;; [route-name params query-params]
(rf/reg-fx
 :navigate!
 (fn [route-or-vec]
   (if (vector? route-or-vec)
     (let [[route-name params query] route-or-vec]
       (rfe/push-state route-name (or params {}) (or query {})))
     (rfe/push-state route-or-vec))))

