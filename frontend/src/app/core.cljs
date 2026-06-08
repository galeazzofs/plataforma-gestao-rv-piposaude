(ns app.core
  (:require [reagent.dom :as rdom]
            [re-frame.core :as rf]
            ;; Wire up state — side-effecting requires register events/subs
            [app.state.events]
            [app.state.subs]
            ;; Toast notifications
            [app.ds.toast]
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
            ;; Líder de Vendas views — Chunk 3
            [app.views.lider-vendas.events]
            [app.views.lider-vendas.subs]
            [app.views.lider-vendas.dashboard :as lider-vendas-dashboard]
            [app.views.lider-vendas.ev-detail :as lider-vendas-ev-detail]
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
            [app.views.revops.appraisal-preview :as revops-appraisal-preview]
            [app.views.revops.contestations :as revops-contestations]
            [app.views.revops.sync-status :as revops-sync-status]
            [app.views.revops.audit-log :as revops-audit-log]
            [app.views.revops.settings :as revops-settings]
            [app.views.revops.policies :as revops-policies]
            [app.views.revops.achievements :as revops-achievements]
            ;; CN views — new commission features
            [app.views.cn.simulator :as cn-simulator]
            [app.views.cn.dashboard :as cn-dashboard]
            ;; RevOps commission views — new commission features
            [app.views.revops.cn-goals :as revops-cn-goals]
            [app.views.revops.cn-appraisal :as revops-cn-appraisal]
            [app.views.revops.ev-bonus :as revops-ev-bonus]
            [app.views.revops.cn-quarterly-bonus :as revops-cn-quarterly-bonus]
            [app.views.revops.leadership-appraisal :as revops-leadership]
            [app.views.revops.quarterly-cycle :as revops-quarterly-cycle]))

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

        ;; Líder de Vendas views
        :lider-vendas/dashboard  [lider-vendas-dashboard/lider-vendas-dashboard-page]
        :lider-vendas/ev-detail  [lider-vendas-ev-detail/ev-detail-page]

        ;; Finance views
        :finance/dashboard  [finance-dashboard/finance-dashboard-page]
        :finance/approval   [finance-approval/approval-page]

        ;; RevOps / Admin views
        :revops/dashboard        [revops-dashboard/revops-dashboard-page]
        :revops/policies         [revops-policies/policies-page]
        :revops/users            [revops-users/users-page]
        :revops/teams            [revops-teams/teams-page]
        :revops/goals            [revops-goals/goals-page]
        :revops/achievements     [revops-achievements/achievements-page]
        :revops/commission-table [revops-commission-table/commission-table-page]
        :revops/financial        [revops-financial-upload/financial-upload-page]
        :revops/appraisal        [revops-appraisal/appraisal-page]
        :revops/appraisal-preview [revops-appraisal-preview/page]
        :revops/appraisal-review [revops-appraisal-review/appraisal-review-page]
        :revops/contestations    [revops-contestations/contestations-page]
        :revops/sync-status      [revops-sync-status/sync-status-page]
        :revops/audit-log        [revops-audit-log/audit-log-page]
        :revops/settings         [revops-settings/settings-page]

        ;; CN views
        :cn/simulator   [cn-simulator/page]
        :cn/dashboard   [cn-dashboard/page]

        ;; RevOps commission views
        :revops/cn-goals      [revops-cn-goals/page]
        :revops/cn-appraisal  [revops-cn-appraisal/page]
        :revops/ev-bonus              [revops-ev-bonus/page]
        :revops/cn-quarterly-bonus    [revops-cn-quarterly-bonus/page]
        :revops/leadership            [revops-leadership/page]
        :revops/quarterly-cycle       [revops-quarterly-cycle/page]

        ;; Fallback — 404
        [not-found-view/page]))))

;; ---------------------------------------------------------------------------
;; App root
;; ---------------------------------------------------------------------------

(defn app-root []
  [:<>
   [route-view]
   [app.ds.toast/toast-container]])

;; ---------------------------------------------------------------------------
;; Entry point
;; ---------------------------------------------------------------------------

(defn ^:export init! []
  (rf/dispatch-sync [:initialize-db])
  (routes/init-routing!)
  (rdom/render [app-root]
               (.getElementById js/document "app")))
