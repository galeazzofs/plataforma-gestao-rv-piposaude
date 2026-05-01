(ns app.api.endpoints)

;; Auth
(def auth-google    "/auth/google")
(def auth-dev-login "/auth/dev-login")
(def auth-refresh   "/auth/refresh")

;; Commissions
(def commissions-summary    "/commissions/summary")
(def commissions-projection "/commissions/projection")

;; Policies
(def policies "/policies")
(defn policy-edit [id] (str "/policies/" id))

;; Validations
(def validations "/validations")
(def validation-approve  (fn [id] (str "/validations/" id "/approve")))
(def validation-contest  (fn [id] (str "/validations/" id "/contest")))

;; Goals
(def goals "/goals")

;; Appraisals
(def appraisals (fn [] "/appraisals"))
(def appraisal-detail (fn [id] (str "/appraisals/" id)))
(def appraisal-recalculate (fn [id] (str "/appraisals/" id "/recalculate")))

;; Achievements (per EV per quarter — manual editor)
(def achievements "/admin/ev-achievements")
(def achievements-calculate "/admin/ev-achievements/calculate")

;; Finance
(def finance-dashboard "/finance/dashboard")
(def finance-approval  "/finance/approval")

;; Admin
(def users    "/admin/users")
(def teams    "/admin/teams")
(defn team-members [team-id] (str "/admin/teams/" team-id "/members"))
(defn team-member  [team-id user-id] (str "/admin/teams/" team-id "/members/" user-id))
(def commission-table "/admin/commission-table")
(def financial-upload "/financial/upload")
(def perk-upload "/financial/upload-perks")
(def settings "/admin/settings")
(def sync-status    "/admin/sync-status")
(def sync-trigger   "/admin/sync-trigger")
(def audit-log   "/admin/audit-log")

;; CN commissions
(def cn-goals           "/commissions/cn/goals")
(def cn-appraisal       "/commissions/cn/appraisal")
(defn cn-appraisal-finalize [id] (str "/commissions/cn/appraisal/" id "/finalize"))
(def cn-simulate        "/commissions/cn/simulate")

;; EV bonus
(def ev-bonus           "/commissions/ev/bonus")

;; Leadership
(def leadership-preview    "/commissions/leadership/preview")
(def leadership-appraisal  "/commissions/leadership/appraisal")
(defn leadership-finalize [id] (str "/commissions/leadership/appraisal/" id "/finalize"))
