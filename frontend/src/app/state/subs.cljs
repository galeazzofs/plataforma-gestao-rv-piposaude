(ns app.state.subs
  (:require [re-frame.core :as rf]))

;; Auth
(rf/reg-sub :auth/user (fn [db _] (get-in db [:auth :user])))
(rf/reg-sub :auth/role (fn [db _] (get-in db [:auth :user :role])))
(rf/reg-sub :auth/logged-in? (fn [db _] (some? (get-in db [:auth :access-token]))))
(rf/reg-sub :auth/loading? (fn [db _] (get-in db [:auth :loading?])))
(rf/reg-sub :auth/error (fn [db _] (get-in db [:auth :error])))

;; UI
(rf/reg-sub :ui/toast (fn [db _] (get-in db [:ui :toast])))
(rf/reg-sub :ui/active-modal (fn [db _] (get-in db [:ui :active-modal])))

;; Notifications
(rf/reg-sub :notifications/items (fn [db _] (get-in db [:notifications :items])))
(rf/reg-sub :notifications/unread-count (fn [db _] (get-in db [:notifications :unread-count])))
