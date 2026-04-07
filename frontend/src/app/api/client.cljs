(ns app.api.client
  (:require [ajax.core :as ajax]
            [clojure.string :as str]
            [re-frame.core :as rf]
            [app.config :as config]))

(defn api-url [path]
  (str config/api-base-url path))

;; Raw token subscription — used internally by the :http effect
(rf/reg-sub
 :auth/access-token-raw
 (fn [db _] (get-in db [:auth :access-token])))

(defn- file-like? [v]
  (or (instance? js/File v)
      (instance? js/Blob v)
      (instance? js/FormData v)))

(defn- ->form-data [body]
  (if (instance? js/FormData body)
    body
    (let [fd (js/FormData.)]
      (.append fd "file" body (or (.-name body) "upload.bin"))
      fd)))

(defn- handle-callback [on-success on-failure ok response]
  (if ok
    (when on-success (rf/dispatch (conj on-success response)))
    (do
      (when (= 401 (:status response))
        (rf/dispatch [:auth/try-refresh]))
      (when on-failure (rf/dispatch (conj on-failure response))))))

(defn- fetch-multipart!
  "Native fetch-based multipart upload. cljs-ajax doesn't pass FormData
  through cleanly because it serializes :params via the chosen format."
  [{:keys [url method body token headers on-success on-failure]}]
  (let [fd (->form-data body)
        h  (clj->js (cond-> headers
                      token (assoc "Authorization" (str "Bearer " token))))]
    (-> (js/fetch (api-url url)
                  #js {:method  (str/upper-case (name method))
                       :headers h
                       :body    fd})
        (.then (fn [resp]
                 (-> (.text resp)
                     (.then (fn [text]
                              (let [parsed (try (js->clj (.parse js/JSON text) :keywordize-keys true)
                                                (catch :default _ nil))]
                                (handle-callback on-success on-failure
                                                 (.-ok resp)
                                                 (or parsed {:status (.-status resp)}))))))))
        (.catch (fn [_]
                  (handle-callback on-success on-failure false {:status 0}))))))

(rf/reg-fx
 :http
 (fn [{:keys [method url body on-success on-failure headers]}]
   (let [token @(rf/subscribe [:auth/access-token-raw])]
     (if (file-like? body)
       (fetch-multipart! {:url url :method method :body body :token token
                          :headers headers :on-success on-success :on-failure on-failure})
       (let [default-headers (cond-> {"Content-Type" "application/json"}
                               token (assoc "Authorization" (str "Bearer " token)))]
         (ajax/ajax-request
          {:uri     (api-url url)
           :method  method
           :headers (merge default-headers headers)
           :params  body
           :format          (ajax/json-request-format)
           :response-format (ajax/json-response-format {:keywords? true})
           :handler (fn [[ok response]]
                      (handle-callback on-success on-failure ok response))}))))))
