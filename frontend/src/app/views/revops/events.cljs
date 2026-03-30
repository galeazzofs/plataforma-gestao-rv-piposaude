(ns app.views.revops.events
  (:require [re-frame.core :as rf]
            [app.api.endpoints :as ep]))

;; ---- Users ----

(rf/reg-event-fx
 :revops/fetch-users
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :users-loading?] true)
    :http {:method     :get
           :url        ep/users
           :on-success [:revops/users-loaded]
           :on-failure [:revops/users-error]}}))

(rf/reg-event-db
 :revops/users-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :users]          (:data response))
       (assoc-in [:admin :users-loading?] false))))

(rf/reg-event-db
 :revops/users-error
 (fn [db _] (assoc-in db [:admin :users-loading?] false)))

(rf/reg-event-fx
 :revops/create-user
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/users
           :body       payload
           :on-success [:revops/fetch-users]
           :on-failure [:revops/user-error]}}))

(rf/reg-event-fx
 :revops/update-user
 (fn [_ [_ id payload]]
   {:http {:method     :patch
           :url        (str ep/users "/" id)
           :body       payload
           :on-success [:revops/fetch-users]
           :on-failure [:revops/user-error]}}))

(rf/reg-event-fx
 :revops/delete-user
 (fn [_ [_ id]]
   {:http {:method     :delete
           :url        (str ep/users "/" id)
           :on-success [:revops/fetch-users]
           :on-failure [:revops/user-error]}}))

(rf/reg-event-db
 :revops/user-error
 (fn [db _]
   (assoc-in db [:ui :toast] {:type :error :message "Erro ao processar usuário."})))

;; ---- Teams ----

(rf/reg-event-fx
 :revops/fetch-teams
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :teams-loading?] true)
    :http {:method     :get
           :url        ep/teams
           :on-success [:revops/teams-loaded]
           :on-failure [:revops/teams-error]}}))

(rf/reg-event-db
 :revops/teams-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :teams]          (:data response))
       (assoc-in [:admin :teams-loading?] false))))

(rf/reg-event-db
 :revops/teams-error
 (fn [db _] (assoc-in db [:admin :teams-loading?] false)))

(rf/reg-event-fx
 :revops/create-team
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/teams
           :body       payload
           :on-success [:revops/fetch-teams]
           :on-failure [:revops/teams-error]}}))

(rf/reg-event-fx
 :revops/update-team
 (fn [_ [_ id payload]]
   {:http {:method     :patch
           :url        (str ep/teams "/" id)
           :body       payload
           :on-success [:revops/fetch-teams]
           :on-failure [:revops/teams-error]}}))

(rf/reg-event-fx
 :revops/delete-team
 (fn [_ [_ id]]
   {:http {:method     :delete
           :url        (str ep/teams "/" id)
           :on-success [:revops/fetch-teams]
           :on-failure [:revops/teams-error]}}))

;; ---- Goals ----

(rf/reg-event-fx
 :revops/fetch-goals
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:goals :loading?] true)
    :http {:method     :get
           :url        ep/goals
           :on-success [:revops/goals-loaded]
           :on-failure [:revops/goals-error]}}))

(rf/reg-event-db
 :revops/goals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:goals :items]    (:data response))
       (assoc-in [:goals :loading?] false))))

(rf/reg-event-db
 :revops/goals-error
 (fn [db _] (assoc-in db [:goals :loading?] false)))

(rf/reg-event-fx
 :revops/update-goal
 (fn [_ [_ id payload]]
   {:http {:method     :put
           :url        (str ep/goals "/" id)
           :body       payload
           :on-success [:revops/fetch-goals]
           :on-failure [:revops/goals-error]}}))

(rf/reg-event-fx
 :revops/import-goals
 (fn [_ [_ file]]
   {:http {:method     :post
           :url        (str ep/goals "/import")
           :body       file
           :on-success [:revops/fetch-goals]
           :on-failure [:revops/goals-error]}}))

;; ---- Commission Table ----

(rf/reg-event-fx
 :revops/fetch-commission-table
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :commission-table-loading?] true)
    :http {:method     :get
           :url        ep/commission-table
           :on-success [:revops/commission-table-loaded]
           :on-failure [:revops/commission-table-error]}}))

(rf/reg-event-db
 :revops/commission-table-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :commission-table]          (get-in response [:data]))
       (assoc-in [:admin :commission-table-loading?] false))))

(rf/reg-event-db
 :revops/commission-table-error
 (fn [db _] (assoc-in db [:admin :commission-table-loading?] false)))

(rf/reg-event-fx
 :revops/create-commission-version
 (fn [_ _]
   {:http {:method     :post
           :url        ep/commission-table
           :on-success [:revops/fetch-commission-table]
           :on-failure [:revops/commission-table-error]}}))

;; ---- Financial Upload ----

(rf/reg-event-fx
 :revops/upload-financial
 (fn [{:keys [db]} [_ file]]
   {:db   (assoc-in db [:admin :upload-loading?] true)
    :http {:method     :post
           :url        ep/financial-upload
           :body       file
           :on-success [:revops/upload-preview-loaded]
           :on-failure [:revops/upload-error]}}))

(rf/reg-event-db
 :revops/upload-preview-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :upload-preview]  (get-in response [:data]))
       (assoc-in [:admin :upload-loading?] false))))

(rf/reg-event-db
 :revops/upload-error
 (fn [db _]
   (-> db
       (assoc-in [:admin :upload-loading?] false)
       (assoc-in [:ui :toast] {:type :error :message "Erro ao processar arquivo."}))))

(rf/reg-event-fx
 :revops/confirm-financial-upload
 (fn [_ [_ upload-id]]
   {:http {:method     :post
           :url        (str "/financial/confirm/" upload-id)
           :on-success [:revops/upload-confirmed]
           :on-failure [:revops/upload-error]}}))

(rf/reg-event-db
 :revops/upload-confirmed
 (fn [db _]
   (-> db
       (assoc-in [:admin :upload-preview] nil)
       (assoc-in [:ui :toast] {:type :success :message "Upload confirmado com sucesso."}))))

(rf/reg-event-db
 :revops/upload-preview-cancel
 (fn [db _]
   (assoc-in db [:admin :upload-preview] nil)))

;; ---- Appraisal ----

(rf/reg-event-fx
 :revops/fetch-appraisals
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:appraisal :loading?] true)
    :http {:method     :get
           :url        (ep/appraisals)
           :on-success [:revops/appraisals-loaded]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-db
 :revops/appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:appraisal :list]     (:data response))
       (assoc-in [:appraisal :loading?] false))))

(rf/reg-event-db
 :revops/appraisals-error
 (fn [db _] (assoc-in db [:appraisal :loading?] false)))

(rf/reg-event-fx
 :revops/create-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        (ep/appraisals)
           :body       payload
           :on-success [:revops/fetch-appraisals]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/run-appraisal
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (ep/appraisal-run id)
           :on-success [:revops/fetch-appraisals]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/approve-appraisal-payment
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (ep/appraisal-approve-payment id)
           :on-success [:revops/fetch-appraisals]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/fetch-appraisal-detail
 (fn [{:keys [db]} [_ id]]
   {:db   (assoc-in db [:appraisal :loading?] true)
    :http {:method     :get
           :url        (ep/appraisal-detail id)
           :on-success [:revops/appraisal-detail-loaded]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-db
 :revops/appraisal-detail-loaded
 (fn [db [_ response]]
   (let [detail (get-in response [:data])]
     (-> db
         ;; Merge detail into the list item that matches
         (update-in [:appraisal :list]
                    (fn [items]
                      (map #(if (= (:id %) (:id detail)) detail %) (or items []))))
         (assoc-in [:appraisal :loading?] false)))))

;; ---- Contestations ----

(rf/reg-event-fx
 :revops/fetch-contestations
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :contestations-loading?] true)
    :http {:method     :get
           :url        "/validations?status=CONTESTED"
           :on-success [:revops/contestations-loaded]
           :on-failure [:revops/contestations-error]}}))

(rf/reg-event-db
 :revops/contestations-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :contestations]         (:data response))
       (assoc-in [:admin :contestations-loading?] false))))

(rf/reg-event-db
 :revops/contestations-error
 (fn [db _] (assoc-in db [:admin :contestations-loading?] false)))

(rf/reg-event-fx
 :revops/resolve-contestation
 (fn [_ [_ id resolution]]
   {:http {:method     :post
           :url        (str "/validations/" id "/resolve")
           :body       {:resolution resolution}
           :on-success [:revops/fetch-contestations]
           :on-failure [:revops/contestations-error]}}))

;; ---- Sync Status ----

(rf/reg-event-fx
 :revops/fetch-sync-status
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :sync-loading?] true)
    :http {:method     :get
           :url        ep/sync-status
           :on-success [:revops/sync-status-loaded]
           :on-failure [:revops/sync-status-error]}}))

(rf/reg-event-db
 :revops/sync-status-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :sync-status]   (get-in response [:data]))
       (assoc-in [:admin :sync-loading?] false))))

(rf/reg-event-db
 :revops/sync-status-error
 (fn [db _] (assoc-in db [:admin :sync-loading?] false)))

(rf/reg-event-fx
 :revops/trigger-sync
 (fn [_ _]
   {:http {:method     :post
           :url        ep/sync-trigger
           :on-success [:revops/fetch-sync-status]
           :on-failure [:revops/sync-status-error]}}))

;; ---- Audit Log ----

(rf/reg-event-fx
 :revops/fetch-audit-log
 (fn [{:keys [db]} [_ filters]]
   {:db   (assoc-in db [:admin :audit-loading?] true)
    :http {:method     :get
           :url        (str ep/audit-log
                            (when filters
                              (str "?" (clojure.string/join "&"
                                        (for [[k v] filters :when v]
                                          (str (name k) "=" v))))))
           :on-success [:revops/audit-log-loaded]
           :on-failure [:revops/audit-log-error]}}))

(rf/reg-event-db
 :revops/audit-log-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :audit-log]     {:items (:data response)
                                          :meta  (:meta response)})
       (assoc-in [:admin :audit-loading?] false))))

(rf/reg-event-db
 :revops/audit-log-error
 (fn [db _] (assoc-in db [:admin :audit-loading?] false)))

;; ---- Settings ----

(rf/reg-event-fx
 :revops/fetch-settings
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :settings-loading?] true)
    :http {:method     :get
           :url        ep/settings
           :on-success [:revops/settings-loaded]
           :on-failure [:revops/settings-error]}}))

(rf/reg-event-db
 :revops/settings-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :settings]         (get-in response [:data]))
       (assoc-in [:admin :settings-loading?] false))))

(rf/reg-event-db
 :revops/settings-error
 (fn [db _] (assoc-in db [:admin :settings-loading?] false)))

(rf/reg-event-fx
 :revops/save-settings
 (fn [_ [_ payload]]
   {:http {:method     :put
           :url        ep/settings
           :body       payload
           :on-success [:revops/fetch-settings]
           :on-failure [:revops/settings-error]}}))
