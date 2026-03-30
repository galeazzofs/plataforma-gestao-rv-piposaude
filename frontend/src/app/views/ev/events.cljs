(ns app.views.ev.events
  (:require [re-frame.core :as rf]
            [app.api.endpoints :as ep]))

(rf/reg-event-fx
 :ev/fetch-dashboard
 (fn [{:keys [db]} _]
   {:db   (-> db
              (assoc-in [:commissions :loading?] true))
    :http {:method     :get
           :url        ep/commissions-summary
           :on-success [:ev/dashboard-loaded]
           :on-failure [:ev/dashboard-error]}}))

(rf/reg-event-db
 :ev/dashboard-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:commissions :summary]  (get-in response [:data :summary]))
       (assoc-in [:commissions :loading?] false))))

(rf/reg-event-db
 :ev/dashboard-error
 (fn [db _]
   (assoc-in db [:commissions :loading?] false)))

(rf/reg-event-fx
 :ev/fetch-policies
 (fn [{:keys [db]} [_ filters]]
   {:db   (assoc-in db [:policies :loading?] true)
    :http {:method     :get
           :url        (str ep/policies
                            (when filters
                              (str "?" (clojure.string/join "&"
                                        (for [[k v] filters :when v]
                                          (str (name k) "=" v))))))
           :on-success [:ev/policies-loaded]
           :on-failure [:ev/policies-error]}}))

(rf/reg-event-db
 :ev/policies-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:policies :items]    (get-in response [:data :items]))
       (assoc-in [:policies :meta]     (get-in response [:data :meta]))
       (assoc-in [:policies :loading?] false))))

(rf/reg-event-db
 :ev/policies-error
 (fn [db _]
   (assoc-in db [:policies :loading?] false)))

(rf/reg-event-fx
 :ev/fetch-projection
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:commissions :loading?] true)
    :http {:method     :get
           :url        ep/commissions-projection
           :on-success [:ev/projection-loaded]
           :on-failure [:ev/projection-error]}}))

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
       (assoc-in [:validations :items]    (get-in response [:data :items]))
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
