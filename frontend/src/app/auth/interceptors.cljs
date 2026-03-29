(ns app.auth.interceptors
  ;; The JWT Authorization header is injected by the :http effect in app.api.client.
  ;; This namespace provides a Re-frame interceptor that can be attached to
  ;; events that require the user to be authenticated, and redirects to login
  ;; if no token is present.
  (:require [re-frame.core :as rf]))

(def require-auth
  (rf/->interceptor
   :id :require-auth
   :before (fn [context]
             (let [db (get-in context [:coeffects :db])
                   token (get-in db [:auth :access-token])]
               (if token
                 context
                 (do
                   (rf/dispatch [:auth/logout])
                   ;; Short-circuit: clear the queue so no event handler runs
                   (assoc context :queue [])))))))
