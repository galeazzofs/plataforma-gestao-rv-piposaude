(ns app.auth.subs
  ;; Auth subscriptions are defined in app.state.subs.
  ;; This namespace re-exports them via require for convenience
  ;; and adds any auth-specific derived subscriptions.
  (:require [re-frame.core :as rf]
            [app.state.subs]))

;; Derived: does the current user have a specific role?
(rf/reg-sub
 :auth/has-role?
 :<- [:auth/role]
 (fn [role [_ required-role]]
   (= role (name required-role))))
