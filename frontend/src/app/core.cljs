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
            ;; Views — always present
            [app.auth.views :as auth-views]
            [app.views.shared.no-role :as no-role-view]
            [app.views.shared.not-found :as not-found-view]))

;; ---------------------------------------------------------------------------
;; Placeholder component for views not yet implemented (Chunks 3+)
;; ---------------------------------------------------------------------------

(defn coming-soon [route-name]
  [:div {:style {:display         "flex"
                 :flex-direction  "column"
                 :align-items     "center"
                 :justify-content "center"
                 :height          "60vh"
                 :gap             "12px"}}
   [:h2 {:style {:font-size   "24px"
                 :font-weight "600"
                 :margin      "0"}}
    "Em breve"]
   [:p {:style {:color  "#6B6B6B"
                :margin "0"}}
    (str "Vista a implementar: " (name (or route-name :unknown)))]])

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
        ;; EV / CN views (implemented in Chunk 3)
        :ev/dashboard   [coming-soon route-name]
        :ev/history     [coming-soon route-name]
        :ev/validation  [coming-soon route-name]

        ;; Gerente views (implemented in Chunk 3)
        :gerente/dashboard  [coming-soon route-name]
        :gerente/ev-detail  [coming-soon route-name]

        ;; Finance views (implemented in Chunk 4)
        :finance/dashboard  [coming-soon route-name]
        :finance/approval   [coming-soon route-name]

        ;; RevOps / Admin views (implemented in Chunk 4)
        :revops/dashboard        [coming-soon route-name]
        :revops/users            [coming-soon route-name]
        :revops/teams            [coming-soon route-name]
        :revops/goals            [coming-soon route-name]
        :revops/commission-table [coming-soon route-name]
        :revops/financial        [coming-soon route-name]
        :revops/appraisal        [coming-soon route-name]
        :revops/appraisal-review [coming-soon route-name]
        :revops/contestations    [coming-soon route-name]
        :revops/sync-status      [coming-soon route-name]
        :revops/audit-log        [coming-soon route-name]
        :revops/settings         [coming-soon route-name]

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
