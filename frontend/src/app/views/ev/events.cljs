(ns app.views.ev.events
  (:require [clojure.string :as str]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]))

(defn- current-period []
  (let [d (js/Date.)
        month (inc (.getMonth d))]
    {:year (.getFullYear d)
     :quarter (inc (js/Math.floor (/ (dec month) 3)))}))

(defn- period-query
  [{:keys [year quarter]}]
  (let [parts (cond-> []
                year    (conj (str "year=" year))
                quarter (conj (str "quarter=" quarter)))]
    (when (seq parts) (str "?" (str/join "&" parts)))))

(defn- dashboard-period [db]
  (or (get-in db [:ev :period]) (current-period)))

(rf/reg-event-fx
 :ev/fetch-dashboard
 (fn [{:keys [db]} _]
   (let [period (dashboard-period db)]
     {:db   (-> db
                (assoc-in [:ev :period] period)
                (assoc-in [:commissions :loading?] true))
      :http {:method     :get
             :url        (str ep/commissions-summary (period-query period))
             :on-success [:ev/dashboard-loaded]
             :on-failure [:ev/dashboard-error]}})))

(rf/reg-event-fx
 :ev/set-period
 (fn [{:keys [db]} [_ kind value]]
   (let [period (assoc (dashboard-period db) kind value)]
     {:db         (assoc-in db [:ev :period] period)
      :dispatch-n [[:ev/fetch-dashboard]
                   [:ev/fetch-policies period]
                   [:ev/fetch-projection]]})))

(rf/reg-event-db
 :ev/dashboard-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:commissions :summary]  (:data response))
       (assoc-in [:commissions :loading?] false))))

(rf/reg-event-db
 :ev/dashboard-error
 (fn [db _]
   (assoc-in db [:commissions :loading?] false)))

(rf/reg-event-fx
 :ev/fetch-policies
 (fn [{:keys [db]} [_ filters]]
   (let [filters (or filters (dashboard-period db))]
     {:db   (-> db
                (assoc-in [:ev :period] filters)
                (assoc-in [:policies :loading?] true))
      :http {:method     :get
             :url        (str ep/policies
                              (when filters
                                (str "?" (str/join "&"
                                          (for [[k v] filters :when v]
                                            (str (name k) "=" v))))))
             :on-success [:ev/policies-loaded]
             :on-failure [:ev/policies-error]}})))

(rf/reg-event-db
 :ev/policies-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:policies :items]    (:data response))
       (assoc-in [:policies :meta]     (:meta response))
       (assoc-in [:policies :loading?] false))))

(rf/reg-event-db
 :ev/policies-error
 (fn [db _]
   (assoc-in db [:policies :loading?] false)))

(rf/reg-event-fx
 :ev/fetch-projection
 (fn [{:keys [db]} _]
   (let [period (dashboard-period db)]
     {:db   (-> db
                (assoc-in [:ev :period] period)
                (assoc-in [:commissions :loading?] true))
      :http {:method     :get
             :url        (str ep/commissions-projection (period-query period))
             :on-success [:ev/projection-loaded]
             :on-failure [:ev/projection-error]}})))

(rf/reg-event-db
 :ev/projection-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:commissions :projection] (get-in response [:data]))
       (assoc-in [:commissions :loading?]   false))))

(rf/reg-event-db
 :ev/projection-error
 (fn [db _]
   (assoc-in db [:commissions :loading?] false)))

;; Fetch ALL of the EV's validations, walking every page. The list endpoint
;; paginates (default 20, max 100 per page); fetching only page 1 used to hide
;; an EV's deals past the 20th — they could never be seen or approved, so
;; "Aprovar todos" left them PENDING and the apuração never advanced.
(def ^:private validations-page-size 100)

(rf/reg-event-fx
 :ev/fetch-validations
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:validations :loading?] true)
    :http {:method     :get
           :url        (str ep/validations "?per_page=" validations-page-size "&page=1")
           :on-success [:ev/validations-page-loaded []]
           :on-failure [:ev/validations-error]}}))

(rf/reg-event-fx
 :ev/validations-page-loaded
 (fn [{:keys [db]} [_ acc response]]
   (let [rows        (into (vec acc) (:data response))
         meta        (:meta response)
         page        (or (:page meta) 1)
         total-pages (or (:total_pages meta) 1)]
     (if (< page total-pages)
       ;; More pages — keep walking, accumulating rows.
       {:http {:method     :get
               :url        (str ep/validations
                                "?per_page=" validations-page-size
                                "&page=" (inc page))
               :on-success [:ev/validations-page-loaded rows]
               :on-failure [:ev/validations-error]}}
       ;; Last page — commit the full list.
       {:db (-> db
                (assoc-in [:validations :items]    rows)
                (assoc-in [:validations :loading?] false))}))))

(rf/reg-event-db
 :ev/validations-error
 (fn [db _]
   (assoc-in db [:validations :loading?] false)))

(defn- set-validation-status
  "Optimistically set one validation row's status (and optional extra fields)
  in-place, leaving the rest of the list untouched."
  [db id status & {:as extra}]
  (update-in db [:validations :items]
             (fn [items]
               (mapv (fn [it]
                       (if (= (:id it) id)
                         (merge it {:status status} extra)
                         it))
                     items))))

;; Approve/contest are the double-submit-prone actions: a quick double-click,
;; or "Aprovar todos" overlapping a single "Aprovar", used to fire a second
;; POST against an already-resolved row → 409. We guard both on two fronts: an
;; in-flight set (`:in-flight`) disables the row's buttons while a request is
;; open, and an optimistic status flip removes the row from "Pendentes" at
;; once. The backend approve is also idempotent now, so even a slipped-through
;; retry is a 200 no-op rather than an error.

(defn- in-flight? [db id]
  (contains? (get-in db [:validations :in-flight] #{}) id))

(defn- mark-in-flight [db id]
  (update-in db [:validations :in-flight] (fnil conj #{}) id))

(defn- clear-in-flight [db id]
  (update-in db [:validations :in-flight] disj id))

(defn- reconcile-row [db id server-row]
  (update-in db [:validations :items]
             (fn [items]
               (mapv #(if (= (:id %) id) (merge % server-row) %) items))))

(rf/reg-event-fx
 :ev/approve-validation
 (fn [{:keys [db]} [_ id]]
   ;; Ignore a repeat dispatch while this id is still in flight.
   (if (in-flight? db id)
     {}
     {:db   (-> db
                (mark-in-flight id)
                (set-validation-status id "APPROVED"))
      :http {:method     :post
             :url        (ep/validation-approve id)
             :on-success [:ev/approve-success id]
             :on-failure [:ev/approve-failure id]}})))

(rf/reg-event-db
 :ev/approve-success
 (fn [db [_ id response]]
   (-> db
       (clear-in-flight id)
       (reconcile-row id (:data response)))))

(rf/reg-event-fx
 :ev/approve-failure
 (fn [{:keys [db]} [_ id response]]
   ;; Either way, undo the optimistic APPROVED flip so a failed refetch can't
   ;; leave the row falsely approved — PENDING is the safe, actionable state.
   (let [db' (-> db (clear-in-flight id) (set-validation-status id "PENDING"))]
     (if (= 409 (:status response))
       ;; Already resolved server-side — refetch the truth, don't hard-error.
       {:db       db'
        :dispatch-n [[:ev/fetch-validations]
                     [:ui/show-toast
                      {:type :warning
                       :message "Esse negócio já não estava pendente. Lista atualizada."}]]}
       {:db       db'
        :dispatch [:ui/show-toast
                   {:type :error :message "Erro ao aprovar. Tente novamente."}]}))))

(rf/reg-event-fx
 :ev/contest-validation
 (fn [{:keys [db]} [_ id comment]]
   (if (in-flight? db id)
     {}
     {:db   (-> db
                (mark-in-flight id)
                (set-validation-status id "CONTESTED" :comment comment))
      :http {:method     :post
             :url        (ep/validation-contest id)
             :body       {:comment comment}
             :on-success [:ev/contest-success id]
             :on-failure [:ev/contest-failure id]}})))

(rf/reg-event-db
 :ev/contest-success
 (fn [db [_ id response]]
   (-> db
       (clear-in-flight id)
       (reconcile-row id (:data response)))))

(rf/reg-event-fx
 :ev/contest-failure
 (fn [{:keys [db]} [_ id response]]
   (let [db' (-> db (clear-in-flight id) (set-validation-status id "PENDING"))]
     (if (= 409 (:status response))
       ;; Already resolved server-side — refetch instead of reverting blind.
       {:db       db'
        :dispatch-n [[:ev/fetch-validations]
                     [:ui/show-toast
                      {:type :warning
                       :message "Esse negócio já não estava pendente. Lista atualizada."}]]}
       {:db       db'
        :dispatch [:ui/show-toast
                   {:type :error :message "Erro ao contestar. Tente novamente."}]}))))
