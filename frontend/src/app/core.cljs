(ns app.core
  (:require [reagent.dom :as rdom]
            [re-frame.core :as rf]
            ;; Wire up state — side-effecting requires register events/subs
            [app.state.events]
            [app.state.subs]
            ;; Wire up auth
            [app.auth.events]
            [app.auth.subs]
            ;; Wire up API client effect handler
            [app.api.client]
            ;; Routing
            [app.routes :as routes]
            ;; Shared views — always present
            [app.auth.views :as auth-views]
            [app.views.shared.no-role :as no-role-view]
            [app.views.shared.not-found :as not-found-view]
            ;; EV views — Chunk 3
            [app.views.ev.events]
            [app.views.ev.subs]
            [app.views.ev.dashboard :as ev-dashboard]
            [app.views.ev.history :as ev-history]
            [app.views.ev.validation :as ev-validation]
            ;; Gerente views — Chunk 3
            [app.views.gerente.events]
            [app.views.gerente.subs]
            [app.views.gerente.dashboard :as gerente-dashboard]
            [app.views.gerente.ev-detail :as gerente-ev-detail]
            ;; Finance views — Chunk 4
            [app.views.finance.events]
            [app.views.finance.subs]
            [app.views.finance.dashboard :as finance-dashboard]
            [app.views.finance.approval :as finance-approval]
            ;; RevOps views — Chunk 4
            [app.views.revops.events]
            [app.views.revops.subs]
            [app.views.revops.dashboard :as revops-dashboard]
            [app.views.revops.users :as revops-users]
            [app.views.revops.teams :as revops-teams]
            [app.views.revops.goals :as revops-goals]
            [app.views.revops.commission-table :as revops-commission-table]
            [app.views.revops.financial-upload :as revops-financial-upload]
            [app.views.revops.appraisal :as revops-appraisal]
            [app.views.revops.appraisal-review :as revops-appraisal-review]
            [app.views.revops.contestations :as revops-contestations]
            [app.views.revops.sync-status :as revops-sync-status]
            [app.views.revops.audit-log :as revops-audit-log]
            [app.views.revops.settings :as revops-settings]
            [app.views.revops.policies :as revops-policies]))

;; ---------------------------------------------------------------------------
;; Route-based view switching
;; ---------------------------------------------------------------------------

(defn route-view []
  (let [route-name @(rf/subscribe [:current-route-name])
        logged-in? @(rf/subscribe [:auth/logged-in?])]
    (cond
      ;; Not authenticated — always show login
      (not logged-in?)
      [auth-views/login-page]

      ;; Logged in but no role assigned
      (= route-name :no-role)
      [no-role-view/no-role-page]

      ;; Authenticated — dispatch to the correct view
      :else
      (case route-name
        ;; EV / CN views
        :ev/dashboard   [ev-dashboard/dashboard-page]
        :ev/history     [ev-history/history-page]
        :ev/validation  [ev-validation/validation-page]

        ;; Gerente views
        :gerente/dashboard  [gerente-dashboard/gerente-dashboard-page]
        :gerente/ev-detail  [gerente-ev-detail/ev-detail-page]

        ;; Finance views
        :finance/dashboard  [finance-dashboard/finance-dashboard-page]
        :finance/approval   [finance-approval/approval-page]

        ;; RevOps / Admin views
        :revops/dashboard        [revops-dashboard/revops-dashboard-page]
        :revops/policies         [revops-policies/policies-page]
        :revops/users            [revops-users/users-page]
        :revops/teams            [revops-teams/teams-page]
        :revops/goals            [revops-goals/goals-page]
        :revops/commission-table [revops-commission-table/commission-table-page]
        :revops/financial        [revops-financial-upload/financial-upload-page]
        :revops/appraisal        [revops-appraisal/appraisal-page]
        :revops/appraisal-review [revops-appraisal-review/appraisal-review-page]
        :revops/contestations    [revops-contestations/contestations-page]
        :revops/sync-status      [revops-sync-status/sync-status-page]
        :revops/audit-log        [revops-audit-log/audit-log-page]
        :revops/settings         [revops-settings/settings-page]

        ;; Fallback — 404
        [not-found-view/page]))))

;; ---------------------------------------------------------------------------
;; App root
;; ---------------------------------------------------------------------------

(defn app-root []
  [route-view])

;; ---------------------------------------------------------------------------
;; Entry point
;; ---------------------------------------------------------------------------

(defn ^:export init! []
  (rf/dispatch-sync [:initialize-db])
  (routes/init-routing!)
  (rdom/render [app-root]
               (.getElementById js/document "app")))
