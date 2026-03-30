(ns app.ds.badge
  (:require [app.ds.tokens :as t]))

(defn badge
  "Simple badge. variant: :default :success :warning :error :info."
  [{:keys [variant]} & children]
  (let [styles {:default {:bg t/bg-subtle :color t/text-secondary}
                :success {:bg t/success-light :color t/success-dark}
                :warning {:bg t/warning-light :color t/warning-dark}
                :error   {:bg t/error-light :color t/error-dark}
                :info    {:bg "#DBEAFE" :color t/blue-700}}
        s (get styles (or variant :default))]
    (into [:span {:style {:display "inline-flex"
                          :align-items "center"
                          :padding "2px 8px"
                          :font-size (:xs t/font-sizes)
                          :font-weight (:medium t/font-weights)
                          :border-radius (:full t/border-radius)
                          :background (:bg s)
                          :color (:color s)}}]
          children)))

(defn status-badge
  "Badge that maps commission/appraisal status to visual style."
  [{:keys [status]}]
  (let [config {"PROJECTED"     {:label "Projetado" :variant :default}
                "IN_PAYMENT"    {:label "Em pagamento" :variant :info}
                "SETTLED"       {:label "Quitado" :variant :success}
                "CANCELLED"     {:label "Cancelado" :variant :error}
                "DRAFT"         {:label "Rascunho" :variant :default}
                "CALCULATING"   {:label "Calculando" :variant :warning}
                "VALIDATING"    {:label "Validação" :variant :info}
                "REVIEWING"     {:label "Revisão" :variant :warning}
                "APPROVED"      {:label "Aprovado" :variant :success}
                "LOCKED"        {:label "Fechado" :variant :success}
                "PENDING"       {:label "Pendente" :variant :default}
                "CONTESTED"     {:label "Contestado" :variant :error}
                "RESOLVED"      {:label "Resolvido" :variant :success}
                "AUTO_APPROVED" {:label "Auto-aprovado" :variant :success}}
        {:keys [label variant]} (get config status {:label status :variant :default})]
    [badge {:variant variant} label]))
