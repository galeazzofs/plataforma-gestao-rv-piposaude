(ns app.auth.events
  (:require [re-frame.core :as rf]
            [app.api.endpoints :as ep]))

(rf/reg-event-fx
 :auth/google-login
 (fn [{:keys [db]} [_ google-code]]
   {:db   (assoc-in db [:auth :loading?] true)
    :http {:method     :post
           :url        ep/auth-google
           :body       {:code google-code}
           :on-success [:auth/login-success]
           :on-failure [:auth/login-failure]}}))

(rf/reg-event-fx
 :auth/dev-login
 (fn [{:keys [db]} [_ email]]
   {:db   (assoc-in db [:auth :loading?] true)
    :http {:method     :post
           :url        ep/auth-dev-login
           :body       {:email email}
           :on-success [:auth/login-success]
           :on-failure [:auth/login-failure]}}))

(rf/reg-event-fx
 :auth/login-success
 (fn [{:keys [db]} [_ response]]
   (let [data (:data response)]
     {:db (-> db
              (assoc-in [:auth :user]          (:user data))
              (assoc-in [:auth :access-token]  (:access_token data))
              (assoc-in [:auth :refresh-token] (:refresh_token data))
              (assoc-in [:auth :loading?]      false)
              (assoc-in [:auth :error]         nil))
      :navigate! (case (get-in data [:user :role])
                   "ADMIN"   :revops/dashboard
                   "FINANCE" :finance/dashboard
                   "LIDER_VENDAS" :lider-vendas/dashboard
                   "EV"      :ev/dashboard
                   "CN"      :cn/dashboard
                   :no-role)})))

(rf/reg-event-db
 :auth/login-failure
 (fn [db [_ _error]]
   (-> db
       (assoc-in [:auth :loading?] false)
       (assoc-in [:auth :error]    "Falha no login. Tente novamente."))))

(rf/reg-event-fx
 :auth/try-refresh
 (fn [{:keys [db]} _]
   (let [refresh-token (get-in db [:auth :refresh-token])]
     (when refresh-token
       {:http {:method     :post
               :url        ep/auth-refresh
               :body       {:refresh_token refresh-token}
               :on-success [:auth/refresh-success]
               :on-failure [:auth/logout]}}))))

(rf/reg-event-db
 :auth/refresh-success
 (fn [db [_ response]]
   (assoc-in db [:auth :access-token] (get-in response [:data :access_token]))))

(rf/reg-event-fx
 :auth/logout
 (fn [{:keys [db]} _]
   {:db (-> db
            (assoc-in [:auth :user]          nil)
            (assoc-in [:auth :access-token]  nil)
            (assoc-in [:auth :refresh-token] nil))
    :navigate! :login}))
