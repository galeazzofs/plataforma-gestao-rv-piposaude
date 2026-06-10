(ns app.views.revops.subs
  (:require [re-frame.core :as rf]))

(rf/reg-sub
 :revops/users
 (fn [db _]
   (get-in db [:admin :users])))

(rf/reg-sub
 :revops/users-loading?
 (fn [db _]
   (get-in db [:admin :users-loading?])))

(rf/reg-sub
 :revops/teams
 (fn [db _]
   (get-in db [:admin :teams])))

(rf/reg-sub
 :revops/teams-loading?
 (fn [db _]
   (get-in db [:admin :teams-loading?])))

(rf/reg-sub
 :revops/goals
 (fn [db _]
   (get-in db [:goals :items])))

(rf/reg-sub
 :revops/goals-loading?
 (fn [db _]
   (get-in db [:goals :loading?])))

(rf/reg-sub
 :revops/commission-table
 (fn [db _]
   (get-in db [:admin :commission-table])))

(rf/reg-sub
 :revops/commission-table-meta
 (fn [db _]
   (get-in db [:admin :commission-table-meta])))

(rf/reg-sub
 :revops/commission-table-loading?
 (fn [db _]
   (get-in db [:admin :commission-table-loading?])))

(rf/reg-sub
 :revops/upload-preview
 (fn [db _]
   (get-in db [:admin :upload-preview])))

(rf/reg-sub
 :revops/upload-result
 (fn [db _]
   (get-in db [:admin :upload-result])))

(rf/reg-sub
 :revops/upload-loading?
 (fn [db _]
   (get-in db [:admin :upload-loading?])))

(rf/reg-sub
 :revops/perk-upload-result
 (fn [db _]
   (get-in db [:admin :perk-upload-result])))

(rf/reg-sub
 :revops/perk-upload-loading?
 (fn [db _]
   (get-in db [:admin :perk-upload-loading?])))

(rf/reg-sub
 :revops/appraisals
 (fn [db _]
   (get-in db [:appraisal :list])))

(rf/reg-sub
 :revops/appraisal-loading?
 (fn [db _]
   (get-in db [:appraisal :loading?])))

(rf/reg-sub
 :revops/contestations
 (fn [db _]
   (get-in db [:admin :contestations])))

(rf/reg-sub
 :revops/contestations-loading?
 (fn [db _]
   (get-in db [:admin :contestations-loading?])))

(rf/reg-sub
 :revops/sync-status
 (fn [db _]
   (get-in db [:admin :sync-status])))

(rf/reg-sub
 :revops/sync-loading?
 (fn [db _]
   (get-in db [:admin :sync-loading?])))

(rf/reg-sub
 :revops/audit-log
 (fn [db _]
   (get-in db [:admin :audit-log])))

(rf/reg-sub
 :revops/audit-loading?
 (fn [db _]
   (get-in db [:admin :audit-loading?])))

(rf/reg-sub
 :revops/settings
 (fn [db _]
   (get-in db [:admin :settings])))

(rf/reg-sub
 :revops/settings-loading?
 (fn [db _]
   (get-in db [:admin :settings-loading?])))

(rf/reg-sub
 :revops/policies
 (fn [db _]
   (get-in db [:admin :policies])))

(rf/reg-sub
 :revops/policies-meta
 (fn [db _]
   (get-in db [:admin :policies-meta])))

(rf/reg-sub
 :revops/policies-loading?
 (fn [db _]
   (get-in db [:admin :policies-loading?])))

(rf/reg-sub
 :revops/ev-users
 :<- [:revops/users]
 (fn [users _]
   (filterv #(= (:role %) "EV") (or users []))))

(rf/reg-sub
 :revops/achievements
 (fn [db _]
   (get-in db [:admin :achievements])))

(rf/reg-sub
 :revops/achievements-loading?
 (fn [db _]
   (get-in db [:admin :achievements-loading?])))

(rf/reg-sub
 :revops/monthly-cycles
 (fn [db _]
   (get-in db [:appraisal :monthly-cycles])))

(rf/reg-sub
 :revops/monthly-cycle
 (fn [db _]
   (get-in db [:appraisal :monthly-cycle])))

(rf/reg-sub
 :revops/monthly-cycle-loading?
 (fn [db _]
   (get-in db [:appraisal :monthly-cycle-loading?])))

(rf/reg-sub
 :revops/preview-result
 (fn [db _]
   (get-in db [:appraisal :preview :result])))

(rf/reg-sub
 :revops/preview-loading?
 (fn [db _]
   (get-in db [:appraisal :preview :loading?])))

(rf/reg-sub
 :revops/preview-error
 (fn [db _]
   (get-in db [:appraisal :preview :error])))
