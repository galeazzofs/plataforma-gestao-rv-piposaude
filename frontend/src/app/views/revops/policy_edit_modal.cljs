(ns app.views.revops.policy-edit-modal
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]))

(defn- ->form [policy]
  (let [seg (:segment policy)
        seg-str (cond
                  (string? seg) seg
                  (keyword? seg) (name seg)
                  :else "")]
    {:ev_id                     (or (:ev_id policy) "")
     :first_payment_real        (or (:first_payment_real policy) "")
     :closed_date               (or (:closed_date policy) "")
     :initial_installments_paid (or (:initial_installments_paid policy) 0)
     :segment                   seg-str
     :partner_operator          (or (:partner_operator policy) "")
     :client_id                 (or (:client_id policy) "")}))

(defn- payload [form]
  ;; Strip empty strings before sending
  (into {} (remove (fn [[_ v]] (or (nil? v) (= "" v))) form)))

(defn policy-edit-modal []
  (let [form (r/atom nil)
        last-id (r/atom nil)]
    (fn [{:keys [open? on-close policy]}]
      ;; Re-init form when policy changes
      (when (and policy (not= (:id policy) @last-id))
        (reset! form (->form policy))
        (reset! last-id (:id policy)))
      [modal/modal
       {:open? open?
        :on-close on-close
        :title (str "Editar Apólice "
                    (or (:hubspot_ticket_id policy)
                        (some-> (:id policy) str (subs 0 8))))
        :size :md}
       (when @form
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [:div {:style {:padding "10px 12px" :background t/beige-100
                         :border-radius (:md t/border-radius)
                         :font-size (:xs t/font-sizes)
                         :color t/text-secondary}}
           "⚠️ Ao salvar, a apólice será marcada como ‘locked’. O sync do HubSpot "
           "não vai sobrescrever esses campos até você desbloquear."]

          [inputs/input
           {:label "Início Vigência (first_payment_real)"
            :type "date"
            :value (:first_payment_real @form)
            :on-change #(swap! form assoc :first_payment_real %)}]

          [inputs/input
           {:label "Data de Gongo (closed_date)"
            :type "date"
            :value (:closed_date @form)
            :on-change #(swap! form assoc :closed_date %)}]

          [inputs/input
           {:label "Parcelas pagas antes da plataforma (0–12)"
            :type "number"
            :value (str (:initial_installments_paid @form))
            :on-change #(swap! form assoc :initial_installments_paid
                               (max 0 (min 12 (or (js/parseInt %) 0))))}]

          [inputs/select
           {:label "Segmento"
            :value (:segment @form)
            :options [{:value "PP" :label "PP"}
                      {:value "P"  :label "P"}
                      {:value "M"  :label "M"}
                      {:value "G"  :label "G"}]
            :on-change #(swap! form assoc :segment %)}]

          [inputs/input
           {:label "Operadora"
            :value (:partner_operator @form)
            :on-change #(swap! form assoc :partner_operator %)}]

          [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"
                         :padding-top "8px"
                         :border-top (str "1px solid " t/border-default)}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button {:variant :primary
                        :on-click (fn []
                                    (rf/dispatch [:revops/update-policy
                                                  (:id policy)
                                                  (payload @form)])
                                    (reset! last-id nil)
                                    (on-close))}
            "Salvar"]]])])))
