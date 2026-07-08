(ns app.views.revops.events
  (:require [re-frame.core :as rf]
            [app.api.endpoints :as ep]))

;; ---- Users ----

(defn fetch-users-fx [db]
  {:db   (assoc-in db [:admin :users-loading?] true)
   :http {:method     :get
          :url        ep/users
          :on-success [:revops/users-loaded]
          :on-failure [:revops/users-error]}})

(rf/reg-event-fx
 :revops/fetch-users
 (fn [{:keys [db]} _]
   (fetch-users-fx db)))

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
 (fn [{:keys [db]} [_ file year]]
   (let [fd (js/FormData.)]
     (.append fd "file" file)
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
 (fn [{:keys [db]} [_ file year]]
   (let [fd (js/FormData.)]
     (.append fd "file" file)
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
 (fn [_ [_ id resp]]
   (let [invalidated (get-in resp [:signoffs :invalidated])
         shown       (take 5 invalidated)
         more        (- (count invalidated) (count shown))
         msg (if (seq invalidated)
               (str "Recalculado. Conferências invalidadas: "
                    (clojure.string/join ", " shown)
                    (when (pos? more) (str " (+" more ")")))
               "Recalculado!")]
     {:dispatch-n [[:revops/fetch-appraisal-detail id]
                   [:ui/show-toast {:type :success :message msg}]]})))

(rf/reg-event-fx
 :revops/release-to-validation
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/transition")
           :body       {:to "VALIDATING"}
           :on-success [:revops/validation-released]
           :on-failure [:revops/release-blocked]}}))

(rf/reg-event-fx
 :revops/release-blocked
 (fn [_ [_ resp]]
   ;; cljs-ajax aninha o body de erro em :response; o caminho direto fica
   ;; como fallback defensivo (mesmo padrão de lider_vendas/events.cljs).
   (let [msg (or (get-in resp [:response :error :message])
                 (get-in resp [:error :message])
                 "Não foi possível liberar para validação.")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))

;; ---- Conferência por EV (sign-off) ----

(rf/reg-event-fx
 :revops/signoff-ev
 (fn [_ [_ appraisal-id ev-id]]
   {:http {:method     :post
           :url        (ep/appraisal-signoff appraisal-id ev-id)
           :on-success [:revops/signoff-updated appraisal-id]
           :on-failure [:revops/signoff-error]}}))

(rf/reg-event-fx
 :revops/reopen-signoff
 (fn [_ [_ appraisal-id ev-id]]
   {:http {:method     :delete
           :url        (ep/appraisal-signoff appraisal-id ev-id)
           :on-success [:revops/signoff-updated appraisal-id]
           :on-failure [:revops/signoff-error]}}))

(rf/reg-event-db
 :revops/signoff-updated
 ;; Merge do delta (signoff do EV + totais) no item da lista — sem refetch
 ;; do detail inteiro a cada clique da esteira de conferência.
 (fn [db [_ appraisal-id response]]
   (let [{:keys [ev_id signoff signoff_totals]} (:data response)]
     (update-in db [:appraisal :list]
                (fn [items]
                  (map (fn [a]
                         (if (= (:id a) appraisal-id)
                           (-> a
                               (assoc :signoff_totals signoff_totals)
                               (update :ev_summary
                                       (fn [evs]
                                         (mapv #(if (= (:ev_id %) ev_id)
                                                  (assoc % :signoff signoff)
                                                  %)
                                               (or evs [])))))
                           a))
                       (or items [])))))))

(rf/reg-event-fx
 :revops/signoff-error
 (fn [_ [_ resp]]
   (let [msg (or (get-in resp [:response :error :message])
                 (get-in resp [:error :message])
                 "Erro ao atualizar a conferência.")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))

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

;; State-aware advance actions for the review page header.
(rf/reg-event-fx
 :revops/advance-to-revops
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/transition")
           :body       {:to "REVOPS_REVIEW"}
           :on-success [:revops/appraisal-advanced id "Enviado para revisão do RevOps."]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/lock-appraisal
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/transition")
           :body       {:to "LOCKED"}
           :on-success [:revops/appraisal-advanced id "Apuração fechada e pagamento liberado."]
           :on-failure [:revops/appraisals-error]}}))

(rf/reg-event-fx
 :revops/appraisal-advanced
 (fn [_ [_ id msg _resp]]
   {:dispatch-n [[:revops/fetch-appraisal-detail id]
                 [:revops/fetch-appraisals]
                 [:ui/show-toast {:type :success :message msg}]]}))

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

;; ---- Monthly preview (read-only draft of Comissão EV) ----

(rf/reg-event-fx
 :revops/run-preview
 (fn [{:keys [db]} [_ {:keys [month year]}]]
   {:db   (-> db
              (assoc-in [:appraisal :preview :loading?] true)
              (assoc-in [:appraisal :preview :error] nil))
    :http {:method     :post
           :url        ep/appraisal-preview
           :body       {:month month :year year}
           :on-success [:revops/preview-success]
           :on-failure [:revops/preview-failure]}}))

(rf/reg-event-db
 :revops/preview-success
 (fn [db [_ response]]
   (-> db
       (assoc-in [:appraisal :preview :result]   (:data response))
       (assoc-in [:appraisal :preview :error]    nil)
       (assoc-in [:appraisal :preview :loading?] false))))

(rf/reg-event-fx
 :revops/preview-failure
 (fn [{:keys [db]} [_ resp]]
   (let [msg (or (get-in resp [:error :message]) "Erro ao gerar a prévia")]
     {:db (-> db
              (assoc-in [:appraisal :preview :loading?] false)
              (assoc-in [:appraisal :preview :error]    msg)
              (assoc-in [:appraisal :preview :result]   nil))
      :dispatch [:ui/show-toast {:type :error :message msg}]})))

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
     {:db (-> db
              (update-in [:admin :policies]
                         (fn [items]
                           (mapv #(if (= (:id %) id) (merge % updated) %) (or items []))))
              (assoc-in [:admin :last-updated-policy] updated))
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
 :revops/resolve-validation-contestation
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

(defn- ->query-string [params]
  (let [qs (js/URLSearchParams.)]
    (doseq [[k v] (or params {})
            :when (and v (not= v ""))]
      (.append qs (name k) (str v)))
    (.toString qs)))

(rf/reg-event-fx
 :revops/fetch-policies
 (fn [{:keys [db]} [_ params]]
   (let [qs (->query-string params)]
     {:db   (-> db
                 (assoc-in [:admin :policies-loading?] true)
                 (assoc-in [:admin :policies-filters] params))
      :http {:method     :get
             :url        (str ep/policies (when (seq qs) (str "?" qs)))
             :on-success [:revops/policies-loaded]
             :on-failure [:revops/policies-error]}})))

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

;; ---- Monthly Cycles ----

(rf/reg-event-fx
 :revops/fetch-monthly-cycles
 (fn [_ _]
   {:http {:method     :get
           :url        "/monthly-cycles"
           :on-success [:revops/monthly-cycles-loaded]
           :on-failure [:revops/monthly-cycles-error]}}))

(rf/reg-event-fx
 :revops/fetch-monthly-cycle-detail
 (fn [{:keys [db]} [_ id]]
   {:db   (-> db
              (assoc-in [:appraisal :monthly-cycle-loading?] true)
              (assoc-in [:appraisal :monthly-cycle-requested-id] id)
              (assoc-in [:appraisal :monthly-cycle-error?] false))
    :http {:method     :get
           :url        (str "/monthly-cycles/" id)
           :on-success [:revops/monthly-cycle-detail-loaded]
           :on-failure [:revops/monthly-cycle-detail-error]}}))

(rf/reg-event-db
 :revops/monthly-cycle-detail-loaded
 (fn [db [_ resp]]
   (-> db
       (assoc-in [:appraisal :monthly-cycle] (:data resp))
       (assoc-in [:appraisal :monthly-cycle-loading?] false))))

(rf/reg-event-db
 :revops/monthly-cycle-detail-error
 (fn [db _]
   (-> db
       (assoc-in [:appraisal :monthly-cycle-loading?] false)
       (assoc-in [:appraisal :monthly-cycle-error?] true))))

(rf/reg-event-db
 :revops/monthly-cycles-loaded
 (fn [db [_ response]]
   (assoc-in db [:appraisal :monthly-cycles] (:data response))))

(rf/reg-event-db
 :revops/monthly-cycles-error
 (fn [db _] db))

(rf/reg-event-fx
 :revops/open-monthly-cycle
 (fn [_ [_ {:keys [month year]}]]
   {:http {:method     :post
           :url        "/monthly-cycles"
           :body       {:month month :year year}
           :on-success [:revops/monthly-cycle-opened]
           :on-failure [:revops/monthly-cycle-open-error]}}))

(rf/reg-event-fx
 :revops/monthly-cycle-opened
 (fn [_ [_ response]]
   (let [c (:data response)
         mm (let [m (:month c)] (if (< m 10) (str "0" m) (str m)))]
     {:dispatch-n [[:revops/fetch-monthly-cycles]
                   [:ui/show-toast
                    {:type :success
                     :message (str "Ciclo " mm "/" (:year c) " aberto.")}]]})))

(rf/reg-event-fx
 :revops/monthly-cycle-open-error
 (fn [_ [_ resp]]
   (let [msg (or (get-in resp [:error :message]) "Erro ao abrir ciclo")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))

(rf/reg-event-fx
 :revops/delete-monthly-cycle
 (fn [{:keys [db]} [_ id]]
   {:db   (-> db
              (update-in [:appraisal :monthly-cycles]
                         (fn [items] (filterv #(not= (:id %) id) (or items []))))
              (update-in [:appraisal]
                         (fn [a] (if (= (get-in a [:monthly-cycle :id]) id)
                                   (dissoc a :monthly-cycle)
                                   a))))
    :http {:method     :delete
           :url        (str "/monthly-cycles/" id)
           :on-success [:revops/monthly-cycle-deleted]
           :on-failure [:revops/monthly-cycle-delete-error]}}))

(rf/reg-event-fx
 :revops/monthly-cycle-deleted
 (fn [_ _]
   {:dispatch-n [[:revops/fetch-monthly-cycles]
                 [:ui/show-toast
                  {:type :success :message "Ciclo mensal excluído."}]]}))

(rf/reg-event-fx
 :revops/monthly-cycle-delete-error
 (fn [_ [_ resp]]
   (let [msg (or (get-in resp [:error :message])
                 "Erro ao excluir ciclo")]
     {:dispatch-n [[:revops/fetch-monthly-cycles]
                   [:ui/show-toast {:type :error :message msg}]]})))

;; ---- Monthly cycle: inline orchestration actions ----
;; One generic event powers every step button on the cycle rail:
;; run the request, then refetch the cycle payload (single source of
;; truth — no optimistic state) and toast the outcome.

(rf/reg-event-db
 :revops/select-cycle-month
 (fn [db [_ selection]]
   (assoc-in db [:appraisal :monthly-cycle-selection] selection)))

(rf/reg-event-fx
 :revops/cycle-action
 (fn [_ [_ {:keys [method url body success-msg cycle-id]}]]
   {:http {:method     (or method :post)
           :url        url
           :body       body
           :on-success [:revops/cycle-action-done cycle-id success-msg]
           :on-failure [:revops/cycle-action-error cycle-id]}}))

(rf/reg-event-fx
 :revops/cycle-action-done
 (fn [_ [_ cycle-id success-msg resp]]
   (let [skipped (get-in resp [:data :skipped])
         msg     (if (seq skipped)
                   (str success-msg " · " (count skipped) " pulado(s)")
                   success-msg)]
     {:dispatch-n
      (cond-> [[:revops/fetch-monthly-cycles]
               [:ui/show-toast {:type :success :message msg}]]
        cycle-id (conj [:revops/fetch-monthly-cycle-detail cycle-id]))})))

(rf/reg-event-fx
 :revops/cycle-action-error
 (fn [_ [_ cycle-id resp]]
   (let [msg (or (get-in resp [:error :message])
                 "Erro ao executar a ação")]
     {:dispatch-n
      (cond-> [[:ui/show-toast {:type :error :message msg}]]
        cycle-id (conj [:revops/fetch-monthly-cycle-detail cycle-id]))})))

;; ---- Appraisal contestation (issue #36) ----

(rf/reg-event-fx
 :revops/contest-appraisal
 (fn [_ [_ id note]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/contest")
           :body       {:note note}
           :on-success [:revops/contestation-action-ok id]
           :on-failure [:revops/contestation-action-err]}}))

(rf/reg-event-fx
 :revops/resolve-appraisal-contestation
 (fn [_ [_ id resolution-note]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/resolve-contestation")
           :body       {:resolution_note resolution-note}
           :on-success [:revops/contestation-action-ok id]
           :on-failure [:revops/contestation-action-err]}}))

(rf/reg-event-fx
 :revops/contestation-action-ok
 (fn [_ [_ id _resp]]
   {:dispatch-n [[:revops/fetch-appraisals]
                 [:revops/fetch-appraisal-detail id]
                 [:ui/show-toast
                  {:type :success :message "Contestação atualizada."}]]}))

(rf/reg-event-fx
 :revops/contestation-action-err
 (fn [_ [_ resp]]
   (let [msg (or (get-in resp [:error :message])
                 "Erro ao processar contestação")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))
