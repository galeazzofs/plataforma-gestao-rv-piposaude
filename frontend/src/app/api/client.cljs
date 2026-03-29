(ns app.api.client
  (:require [ajax.core :as ajax]
            [re-frame.core :as rf]
            [app.config :as config]))

(defn api-url [path]
  (str config/api-base-url path))

;; Raw token subscription — used internally by the :http effect
(rf/reg-sub
 :auth/access-token-raw
 (fn [db _] (get-in db [:auth :access-token])))

(rf/reg-fx
 :http
 (fn [{:keys [method url body on-success on-failure headers]}]
   (let [token @(rf/subscribe [:auth/access-token-raw])
         default-headers (cond-> {"Content-Type" "application/json"}
                           token (assoc "Authorization" (str "Bearer " token)))]
     (ajax/ajax-request
      {:uri     (api-url url)
       :method  method
       :headers (merge default-headers headers)
       :params  body
       :format          (ajax/json-request-format)
       :response-format (ajax/json-response-format {:keywords? true})
       :handler (fn [[ok response]]
                  (if ok
                    (when on-success (rf/dispatch (conj on-success response)))
                    (do
                      ;; Auto-refresh on 401
                      (when (= 401 (:status response))
                        (rf/dispatch [:auth/try-refresh]))
                      (when on-failure (rf/dispatch (conj on-failure response))))))}))))
