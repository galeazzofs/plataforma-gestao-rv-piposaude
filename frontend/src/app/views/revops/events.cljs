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

(rf/reg-event-fx
 :revops/add-team-member
 (fn [_ [_ team-id user-id]]
   {:http {:method     :post
           :url        (ep/team-members team-id)
           :body       {:user_id user-id}
           :on-success [:revops/team-membership-changed]
           :on-failure [:revops/team-membership-error]}}))

(rf/reg-event-fx
 :revops/remove-team-member
 (fn [_ [_ team-id user-id]]
   {:http {:method     :delete
           :url        (ep/team-member team-id user-id)
           :on-success [:revops/team-membership-changed]
           :on-failure [:revops/team-membership-error]}}))

(rf/reg-event-fx
 :revops/team-membership-changed
 (fn [_ _]
   {:dispatch-n [[:revops/fetch-teams]
                 [:revops/fetch-users]
                 [:ui/show-toast {:type :success :message "Time atualizado"}]]}))

(rf/reg-event-fx
 :revops/team-membership-error
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :error :message "Erro ao atualizar membros do time"}]}))

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
 (fn [_ [_ _id payload]]
   {:http {:method     :post
           :url        ep/goals
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
       (assoc-in [:admin :commission-table-meta]     (get-in response [:meta]))
       (assoc-in [:admin :commission-table-loading?] false))))

(rf/reg-event-db
 :revops/commission-table-error
 (fn [db _] (assoc-in db [:admin :commission-table-loading?] false)))

(rf/reg-event-fx
 :revops/create-commission-version
 (fn [{:keys [db]} [_ rows]]
   (let [ct-data  (get-in db [:admin :commission-table])
         version  (inc (or (get-in db [:admin :commission-table-meta :version]) 0))]
     {:http {:method     :post
             :url        ep/commission-table
             :body       (merge {:version version}
                                (when rows {:rows rows}))
             :on-success [:revops/fetch-commission-table]
             :on-failure [:revops/commission-table-error]}})))

;; ---- Financial Upload ----

(rf/reg-event-fx
 :revops/upload-financial
 (fn [{:keys [db]} [_ file quarter year]]
   (let [fd (js/FormData.)]
     (.append fd "file" file)
     (.append fd "quarter" (str quarter))
     (.append fd "year" (str year))
     {:db   (-> db
                (assoc-in [:admin :upload-loading?] true)
                (assoc-in [:admin :upload-result] nil))
      :http {:method     :post
             :url        ep/financial-upload
             :body       fd
             :on-success [:revops/upload-success]
             :on-failure [:revops/upload-error]}})))

(rf/reg-event-fx
 :revops/upload-success
 (fn [{:keys [db]} [_ response]]
   {:db (-> db
            (assoc-in [:admin :upload-result] (:data response))
            (assoc-in [:admin :upload-loading?] false))
    :dispatch [:ui/show-toast
               {:type :success
                :message (str "Upload concluído: "
                              (or (get-in response [:data :rows_persisted]) 0)
                              " linhas persistidas.")}]}))

(rf/reg-event-fx
 :revops/upload-error
 (fn [{:keys [db]} [_ resp]]
   (let [err (or (get-in resp [:error :message]) "Erro ao processar arquivo")]
     {:db (assoc-in db [:admin :upload-loading?] false)
      :dispatch [:ui/show-toast {:type :error :message err}]})))

(rf/reg-event-db
 :revops/upload-reset
 (fn [db _]
   (-> db
       (assoc-in [:admin :upload-result] nil)
       (assoc-in [:admin :upload-loading?] false))))

;; ---- Perk/subsidy upload ----

(rf/reg-event-fx
 :revops/upload-perks
 (fn [{:keys [db]} [_ file quarter year]]
   (let [fd (js/FormData.)]
     (.append fd "file" file)
     (.append fd "quarter" (str quarter))
     (.append fd "year" (str year))
     {:db   (-> db
                (assoc-in [:admin :perk-upload-loading?] true)
                (assoc-in [:admin :perk-upload-result] nil))
      :http {:method     :post
             :url        ep/perk-upload
             :body       fd
             :on-success [:revops/perk-upload-success]
             :on-failure [:revops/perk-upload-error]}})))

(rf/reg-event-fx
 :revops/perk-upload-success
 (fn [{:keys [db]} [_ response]]
   {:db (-> db
            (assoc-in [:admin :perk-upload-result] (:data response))
            (assoc-in [:admin :perk-upload-loading?] false))
    :dispatch [:ui/show-toast
               {:type :success
                :message (str "Upload de subsídios concluído: "
                              (get-in response [:data :matched]) " matched, "
                              (get-in response [:data :missed]) " missed.")}]}))

(rf/reg-event-fx
 :revops/perk-upload-error
 (fn [{:keys [db]} [_ resp]]
   (let [err (or (get-in resp [:error :message]) "Erro ao processar arquivo de subsídios")]
     {:db (assoc-in db [:admin :perk-upload-loading?] false)
      :dispatch [:ui/show-toast {:type :error :message err}]})))

(rf/reg-event-db
 :revops/perk-upload-reset
 (fn [db _]
   (-> db
       (assoc-in [:admin :perk-upload-result] nil)
       (assoc-in [:admin :perk-upload-loading?] false))))

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
           :url        (str "/appraisals/" id "/transition")
           :body       {:to "CALCULATING"}
           :on-success [:revops/appraisal-calculated id]
           :on-failure [:revops/appraisal-calculate-error]}}))

(rf/reg-event-fx
 :revops/appraisal-calculated
 (fn [_ [_ id _resp]]
   {:dispatch-n [[:revops/fetch-appraisals]
                 [:navigate! [:revops/appraisal-review {:id id}]]
                 [:ui/show-toast {:type :success
                                  :message "Cálculo concluído. Revise os valores antes de liberar."}]]}))

(rf/reg-event-fx
 :revops/appraisal-calculate-error
 (fn [_ [_ resp]]
   (let [err (get-in resp [:error] {})
         msg (cond
               (= "MISSING_ACHIEVEMENTS" (:code err))
               (str "Faltam atingimentos: " (clojure.string/join ", " (or (:missing err) [])))
               :else (or (:message err) "Erro ao iniciar cálculo"))]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))

(rf/reg-event-fx
 :revops/recalculate-appraisal
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (ep/appraisal-recalculate id)
           :on-success [:revops/recalculated id]
           :on-failure [:revops/appraisal-calculate-error]}}))

(rf/reg-event-fx
 :revops/recalculated
 (fn [_ [_ id _resp]]
   {:dispatch-n [[:revops/fetch-appraisal-detail id]
                 [:ui/show-toast {:type :success :message "Recalculado!"}]]}))

(rf/reg-event-fx
 :revops/release-to-validation
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/transition")
           :body       {:to "VALIDATING"}
           :on-success [:revops/validation-released]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/validation-released
 (fn [_ _]
   {:dispatch-n [[:revops/fetch-appraisals]
                 [:navigate! :revops/appraisal]
                 [:ui/show-toast {:type :success
                                  :message "Liberado para validação dos EVs."}]]}))

(rf/reg-event-fx
 :revops/approve-appraisal-payment
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/transition")
           :body       {:to "LOCKED"}
           :on-success [:revops/fetch-appraisals]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/delete-appraisal
 (fn [_ [_ id]]
   {:http {:method     :delete
           :url        (ep/appraisal-detail id)
           :on-success [:revops/appraisal-deleted]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/appraisal-deleted
 (fn [_ _]
   {:dispatch-n [[:revops/fetch-appraisals]
                 [:ui/show-toast {:type :success :message "Apuração deletada."}]]}))

;; ---- Edit Policy (manual override) ----

(rf/reg-event-fx
 :revops/update-policy
 (fn [_ [_ id payload]]
   {:http {:method     :put
           :url        (ep/policy-edit id)
           :body       payload
           :on-success [:revops/policy-updated]
           :on-failure [:revops/policy-update-error]}}))

(rf/reg-event-fx
 :revops/policy-updated
 (fn [{:keys [db]} [_ response]]
   (let [updated (get-in response [:data])
         id      (:id updated)]
     {:db (update-in db [:admin :policies]
                     (fn [items]
                       (mapv #(if (= (:id %) id) (merge % updated) %) (or items []))))
      :dispatch [:ui/show-toast {:type :success :message "Apólice atualizada"}]})))

(rf/reg-event-fx
 :revops/policy-update-error
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :error :message "Erro ao atualizar apólice"}]}))

;; ---- Achievements (per EV per quarter) ----

(rf/reg-event-fx
 :revops/fetch-achievements
 (fn [{:keys [db]} [_ {:keys [quarter year]}]]
   {:db   (assoc-in db [:admin :achievements-loading?] true)
    :http {:method :get
           :url (str ep/achievements "?quarter=" quarter "&year=" year)
           :on-success [:revops/achievements-loaded]
           :on-failure [:revops/achievements-error]}}))

(rf/reg-event-db
 :revops/achievements-loaded
 (fn [db [_ resp]]
   (-> db
       (assoc-in [:admin :achievements] (:data resp))
       (assoc-in [:admin :achievements-loading?] false))))

(rf/reg-event-db
 :revops/achievements-error
 (fn [db _] (assoc-in db [:admin :achievements-loading?] false)))

(rf/reg-event-fx
 :revops/save-achievement
 (fn [_ [_ payload]]
   {:http {:method :post
           :url ep/achievements
           :body payload
           :on-success [:revops/achievement-saved payload]
           :on-failure [:revops/achievement-error]}}))

(rf/reg-event-fx
 :revops/achievement-saved
 (fn [_ [_ payload _resp]]
   {:dispatch-n [[:revops/fetch-achievements
                  {:quarter (:quarter payload) :year (:year payload)}]
                 [:ui/show-toast {:type :success :message "Atingimento salvo"}]]}))

(rf/reg-event-fx
 :revops/achievement-error
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :error :message "Erro ao salvar atingimento"}]}))

(rf/reg-event-fx
 :revops/auto-calc-achievements
 (fn [_ [_ {:keys [quarter year] :as payload}]]
   {:http {:method :post
           :url ep/achievements-calculate
           :body payload
           :on-success [:revops/auto-calc-done quarter year]
           :on-failure [:revops/achievement-error]}}))

(rf/reg-event-fx
 :revops/auto-calc-done
 (fn [_ [_ quarter year _resp]]
   {:dispatch-n [[:revops/fetch-achievements {:quarter quarter :year year}]
                 [:ui/show-toast {:type :success
                                  :message "Baseline calculado"}]]}))

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
           :url        (str ep/validations "?status=CONTESTED")
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

(rf/reg-event-fx
 :revops/sync-status-loaded
 (fn [{:keys [db]} [_ response]]
   (let [data    (get-in response [:data])
         running (:running data)
         new-db  (-> db
                     (assoc-in [:admin :sync-status] data)
                     (assoc-in [:admin :sync-loading?] false))]
     (if running
       ;; Sync still running — poll again in 3 seconds
       {:db             new-db
        :dispatch-later [{:ms 3000 :dispatch [:revops/fetch-sync-status]}]}
       ;; Sync finished — stop polling
       {:db new-db}))))

(rf/reg-event-db
 :revops/sync-status-error
 (fn [db _] (assoc-in db [:admin :sync-loading?] false)))

(rf/reg-event-fx
 :revops/trigger-sync
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:admin :sync-loading?] true)
    :http {:method     :post
           :url        ep/sync-trigger
           :on-success [:revops/sync-triggered]
           :on-failure [:revops/sync-status-error]}}))

(rf/reg-event-fx
 :revops/sync-triggered
 (fn [_ _]
   ;; Trigger succeeded — start polling for status
   {:dispatch-later [{:ms 1000 :dispatch [:revops/fetch-sync-status]}]}))

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
           :body       {:settings payload}
           :on-success [:revops/fetch-settings]
           :on-failure [:revops/settings-error]}}))

;; ---- Policies (Admin view all) ----

(rf/reg-event-fx
 :revops/fetch-policies
 (fn [{:keys [db]} [_ params]]
   {:db   (-> db
               (assoc-in [:admin :policies-loading?] true)
               (assoc-in [:admin :policies-filters] params))
    :http {:method     :get
           :url        (str ep/policies
                            "?" (clojure.string/join "&"
                                  (keep (fn [[k v]]
                                          (when (and v (not= v ""))
                                            (str (name k) "=" v)))
                                        (or params {}))))
           :on-success [:revops/policies-loaded]
           :on-failure [:revops/policies-error]}}))

(rf/reg-event-db
 :revops/policies-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :policies]          (:data response))
       (assoc-in [:admin :policies-meta]     (:meta response))
       (assoc-in [:admin :policies-loading?] false))))

(rf/reg-event-db
 :revops/policies-error
 (fn [db _] (assoc-in db [:admin :policies-loading?] false)))
