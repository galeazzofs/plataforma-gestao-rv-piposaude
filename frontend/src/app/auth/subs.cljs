(ns app.auth.subs
  ;; Auth subscriptions are defined in app.state.subs.
  ;; This namespace re-exports them via require for convenience
  ;; and adds any auth-specific derived subscriptions.
  (:require [re-frame.core :as rf]
            [app.state.subs]))

;; Alias — convenient access to the current user map
(rf/reg-sub
 :auth/current-user
 :<- [:auth/user]
 (fn [user _] user))

;; Derived: does the current user have a specific role?
(rf/reg-sub
 :auth/has-role?
 :<- [:auth/role]
 (fn [role [_ required-role]]
   (= role (name required-role))))
