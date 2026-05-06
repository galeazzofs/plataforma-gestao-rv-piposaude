(ns app.views.revops.policy-edit-modal
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.modal :as modal]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]))

(defn- ->form [policy]
  (let [seg (:segment policy)
        seg-str (cond (string? seg) seg (keyword? seg) (name seg) :else "")]
    {:ev_id                     (or (:ev_id policy) "")
     :first_payment_real        (or (:first_payment_real policy) "")
     :closed_date               (or (:closed_date policy) "")
     :initial_installments_paid (or (:initial_installments_paid policy) 0)
     :segment                   seg-str
     :partner_operator          (or (:partner_operator policy) "")
     :client_id                 (or (:client_id policy) "")
     :commission_paid_legacy    (or (:commission_paid_legacy policy) "")
     :total_paid_comissao       (or (:total_paid_comissao policy) "")
     :total_paid_agenciamento   (or (:total_paid_agenciamento policy) "")}))

(defn- payload [form]
  (into {} (remove (fn [[_ v]] (or (nil? v) (= "" v))) form)))

(defn policy-edit-modal []
  (let [form (r/atom nil)
        last-id (r/atom nil)]
    (fn [{:keys [open? on-close policy]}]
      (when (and policy (not= (:id policy) @last-id))
        (reset! form (->form policy))
        (reset! last-id (:id policy)))
      (let [ev-users @(rf/subscribe [:revops/ev-users])]
        [modal/modal
         {:open? open? :on-close on-close
          :title (str "Editar Apólice "
                      (or (:hubspot_ticket_id policy)
                          (some-> (:id policy) str (subs 0 8))))
          :size :md}
         (when @form
           [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
            [:div.callout
             [layout/icon "lock" {:width 20 :height 20}]
             [:div {:style {:flex 1}}
              [:strong "Edição manual trava o sync"]
              [:p {:style {:font-size "12px" :color "var(--fg-3)" :margin-top "2px"}}
               "Ao salvar, a apólice é marcada como locked. O sync do HubSpot não vai sobrescrever esses campos até você desbloquear."]]]

            [inputs/select
             {:label "EV Responsável"
              :value (or (:ev_id @form) "")
              :options (into [{:value "" :label "Sem EV"}]
                             (map (fn [u] {:value (:id u) :label (:name u)}) ev-users))
              :on-change #(swap! form assoc :ev_id %)}]

            [:div.form-grid.-tight
             [inputs/input
              {:label "Início vigência" :type "date"
               :value (:first_payment_real @form)
               :on-change #(swap! form assoc :first_payment_real %)}]
             [inputs/input
              {:label "Data de gongo" :type "date"
               :value (:closed_date @form)
               :on-change #(swap! form assoc :closed_date %)}]]

            [:div.form-grid.-tight
             [inputs/input
              {:label "Parcelas pagas antes da plataforma (0–12)" :type "number"
               :value (str (:initial_installments_paid @form))
               :on-change #(swap! form assoc :initial_installments_paid
                                  (max 0 (min 12 (or (js/parseInt %) 0))))}]
             [inputs/select
              {:label "Segmento" :value (:segment @form)
               :options [{:value "PP" :label "PP"} {:value "P" :label "P"}
                         {:value "M" :label "M"} {:value "G" :label "G"}]
               :on-change #(swap! form assoc :segment %)}]]

            [:div.form-grid.-tight
             [inputs/input
              {:label "Operadora"
               :value (:partner_operator @form)
               :on-change #(swap! form assoc :partner_operator %)}]
             [inputs/input
              {:label "Comissão paga antes da plataforma (R$)" :type "number"
               :value (str (:commission_paid_legacy @form))
               :on-change #(swap! form assoc :commission_paid_legacy %)}]]

            [:div.form-grid.-tight
             [inputs/input
              {:label "Total Pago Comissão (R$)" :type "number"
               :value (str (:total_paid_comissao @form))
               :on-change #(swap! form assoc :total_paid_comissao %)}]
             [inputs/input
              {:label "Total Pago Agenciamento (R$)" :type "number"
               :value (str (:total_paid_agenciamento @form))
               :on-change #(swap! form assoc :total_paid_agenciamento %)}]]

            [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"
                           :padding-top "12px"
                           :border-top "1px solid var(--border-subtle)"}}
             [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
             [btn/button {:variant :primary
                          :on-click (fn []
                                      (rf/dispatch [:revops/update-policy
                                                    (:id policy)
                                                    (payload @form)])
                                      (reset! last-id nil)
                                      (on-close))}
              [layout/icon "check" {:width 14 :height 14}] "Salvar"]]])]))))
