(ns app.views.finance.events
  (:require [clojure.string :as str]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]))

(defn- period-query
  "Build ?year=&quarter= query string from the current finance period filter.
   :all values are dropped — the backend treats their absence as all-time.
   Future buckets travel as stable strings, e.g. \"2027_plus\"."
  [{:keys [year quarter]}]
  (let [parts (cond-> []
                (and year (not= :all year))       (conj (str "year=" year))
                (and quarter (not= :all quarter)) (conj (str "quarter=" quarter)))]
    (when (seq parts) (str "?" (str/join "&" parts)))))

(defn- dashboard-error-message [response]
  (case (:status response)
    0   "A conexão caiu antes de atualizar a visão financeira. Os valores abaixo podem estar desatualizados."
    400 "O período selecionado não pôde ser consultado. Limpe o filtro ou tente outro período."
    401 "Sua sessão expirou antes de atualizar a visão financeira. Entre novamente para ver valores atualizados."
    403 "Seu usuário não tem permissão para atualizar esta visão financeira."
    429 "Muitas atualizações em sequência. Aguarde alguns segundos antes de tentar de novo."
    500 "O servidor não conseguiu atualizar a visão financeira agora. Os valores abaixo podem estar desatualizados."
    "Não conseguimos atualizar a visão financeira. Os valores abaixo podem estar desatualizados."))

(rf/reg-event-fx
 :finance/fetch-dashboard
 (fn [{:keys [db]} _]
   (let [period (or (get-in db [:finance :period]) {:year :all :quarter :all})
         request-id (random-uuid)
         url    (str ep/finance-dashboard (period-query period))]
     {:db   (-> db
                (assoc-in [:finance :loading?] true)
                (assoc-in [:finance :dashboard-error] nil)
                (assoc-in [:finance :dashboard-request-id] request-id))
      :http {:method     :get
             :url        url
             :on-success [:finance/dashboard-loaded request-id]
             :on-failure [:finance/dashboard-error request-id]}})))

(rf/reg-event-fx
 :finance/set-period
 (fn [{:keys [db]} [_ kind value]]
   {:db       (assoc-in db [:finance :period kind] value)
    :dispatch [:finance/fetch-dashboard]}))

(rf/reg-event-fx
 :finance/reset-period
 (fn [{:keys [db]} _]
   {:db       (assoc-in db [:finance :period] {:year :all :quarter :all})
    :dispatch [:finance/fetch-dashboard]}))

(rf/reg-event-db
 :finance/dashboard-loaded
 (fn [db [_ request-id response]]
   (if (= request-id (get-in db [:finance :dashboard-request-id]))
     (-> db
         (assoc-in [:finance :dashboard] (get-in response [:data]))
         (assoc-in [:finance :loading?]  false)
         (assoc-in [:finance :dashboard-error] nil)
         (assoc-in [:finance :dashboard-request-id] nil))
     db)))

(rf/reg-event-db
 :finance/dashboard-error
 (fn [db [_ request-id response]]
   (if (= request-id (get-in db [:finance :dashboard-request-id]))
     (-> db
         (assoc-in [:finance :loading?] false)
         (assoc-in [:finance :dashboard-error] (dashboard-error-message response))
         (assoc-in [:finance :dashboard-request-id] nil))
     db)))

(rf/reg-event-fx
 :finance/fetch-approval
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:finance :approval-loading?] true)
    :http {:method     :get
           :url        ep/finance-approval
           :on-success [:finance/approval-loaded]
           :on-failure [:finance/approval-error]}}))

(rf/reg-event-db
 :finance/approval-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:finance :approval-items]   (get-in response [:data :items]))
       (assoc-in [:finance :approval-loading?] false))))

(rf/reg-event-db
 :finance/approval-error
 (fn [db _]
   (assoc-in db [:finance :approval-loading?] false)))

(rf/reg-event-fx
 :finance/liberar-pagamento
 (fn [_ [_ appraisal-id]]
   {:http {:method     :post
           :url        (str "/appraisals/" appraisal-id "/transition")
           :body       {:to "LOCKED"}
           :on-success [:finance/payment-action-success]
           :on-failure [:finance/payment-action-error]}}))

(rf/reg-event-fx
 :finance/devolver
 (fn [_ [_ appraisal-id]]
   {:http {:method     :post
           :url        (str "/appraisals/" appraisal-id "/transition")
           :body       {:to "REVIEWING"}
           :on-success [:finance/payment-action-success]
           :on-failure [:finance/payment-action-error]}}))

(rf/reg-event-fx
 :finance/payment-action-success
 (fn [_ _]
   {:dispatch [:finance/fetch-approval]}))

(rf/reg-event-db
 :finance/payment-action-error
 (fn [db _]
   (assoc-in db [:ui :toast] {:type :error :message "Erro ao processar ação de pagamento."})))

(rf/reg-event-fx
 :finance/export
 (fn [{:keys [db]} [_ params]]
   (let [base  "/api/v1"
         query (clojure.string/join "&"
                 (for [[k v] params :when v]
                   (str (name k) "=" v)))
         url   (str base "/finance/export" (when (seq query) (str "?" query)))]
     (.open js/window url "_blank")
     {:dispatch [:finance/export-success]})))

(rf/reg-event-db
 :finance/export-success
 (fn [db _]
   (assoc-in db [:ui :toast] {:type :success :message "Exportação iniciada com sucesso."})))

(rf/reg-event-db
 :finance/export-error
 (fn [db _]
   (assoc-in db [:ui :toast] {:type :error :message "Erro ao exportar dados."})))
