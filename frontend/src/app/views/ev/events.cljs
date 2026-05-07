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

(rf/reg-event-fx
 :ev/fetch-validations
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:validations :loading?] true)
    :http {:method     :get
           :url        ep/validations
           :on-success [:ev/validations-loaded]
           :on-failure [:ev/validations-error]}}))

(rf/reg-event-db
 :ev/validations-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:validations :items]    (:data response))
       (assoc-in [:validations :loading?] false))))

(rf/reg-event-db
 :ev/validations-error
 (fn [db _]
   (assoc-in db [:validations :loading?] false)))

(rf/reg-event-fx
 :ev/approve-validation
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (ep/validation-approve id)
           :on-success [:ev/validation-action-success]
           :on-failure [:ev/validation-action-error]}}))

(rf/reg-event-fx
 :ev/contest-validation
 (fn [_ [_ id comment]]
   {:http {:method     :post
           :url        (ep/validation-contest id)
           :body       {:comment comment}
           :on-success [:ev/validation-action-success]
           :on-failure [:ev/validation-action-error]}}))

(rf/reg-event-fx
 :ev/validation-action-success
 (fn [_ _]
   {:dispatch [:ev/fetch-validations]}))

(rf/reg-event-db
 :ev/validation-action-error
 (fn [db _]
   (assoc-in db [:ui :toast] {:type :error :message "Erro ao processar validação."})))
