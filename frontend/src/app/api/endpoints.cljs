(ns app.api.endpoints)

;; Auth
(def auth-google    "/auth/google")
(def auth-refresh   "/auth/refresh")

;; Commissions
(def commissions-summary    "/commissions/summary")
(def commissions-projection "/commissions/projection")

;; Policies
(def policies "/policies")

;; Validations
(def validations "/validations")
(def validation-approve  (fn [id] (str "/validations/" id "/approve")))
(def validation-contest  (fn [id] (str "/validations/" id "/contest")))

;; Goals
(def goals "/goals")

;; Appraisals
(def appraisals (fn [] "/appraisals"))
(def appraisal-detail (fn [id] (str "/appraisals/" id)))
(def appraisal-run (fn [id] (str "/appraisals/" id "/run")))
(def appraisal-approve-payment (fn [id] (str "/appraisals/" id "/approve-payment")))

;; Finance
(def finance-dashboard "/finance/dashboard")
(def finance-approval  "/finance/approval")

;; Admin
(def users    "/admin/users")
(def teams    "/admin/teams")
(def commission-table        "/admin/commission-table")
(def commission-table-import "/admin/commission-table/import")
(def financial-upload "/financial/upload")
(def settings "/admin/settings")
(def sync-status    "/admin/sync-status")
(def sync-trigger   "/admin/sync-trigger")
(def audit-log   "/admin/audit-log")
