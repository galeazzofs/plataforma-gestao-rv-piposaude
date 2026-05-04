(ns app.ds.badge
  (:require [app.ds.tokens :as t]))

;; Badge variants are rendered with a leading status dot, matching the
;; .badge spec from the Pipo design (mono font, pill, dot in `currentColor`).

(defn badge
  "Pill badge with a leading dot.
   variant: :default :success :warning :error :info."
  [{:keys [variant]} & children]
  (let [styles {:default {:bg "#F6F6F6"          :color "#6B6663"}
                :success {:bg t/success-light    :color t/success-default}
                :warning {:bg t/warning-light    :color t/warning-dark}
                :error   {:bg t/error-light      :color t/error-default}
                :info    {:bg "var(--badge-calc-bg)" :color t/blue-700}}
        s (get styles (or variant :default))]
    (into [:span {:style {:display "inline-flex"
                          :align-items "center"
                          :gap "6px"
                          :padding "3px 10px"
                          :font-family t/font-mono
                          :font-size "11px"
                          :font-weight (:medium t/font-weights)
                          :line-height "1.4"
                          :border-radius (:full t/border-radius)
                          :background (:bg s)
                          :color (:color s)
                          :white-space "nowrap"}}
           [:span {:style {:width "6px" :height "6px" :border-radius "50%"
                           :background "currentColor" :flex-shrink "0"}}]]
          children)))

(defn count-pill
  "Mono count indicator for tab labels and section headers.

   Visually quieter than `badge` (no leading dot, no full padding) — the
   number itself is the content. Tonal background+text colors signal
   severity at a glance.

   Props:
     :tone        :neutral (default), :danger, :warning, :info, :success
     :tab-spaced? when true, includes margin-left:6px so the pill sits
                  next to a tab label (default true). Pass false for
                  section-header use where the parent owns the gap.

   Example:
     [count-pill {:tone :danger} (count open-issues)]
     [count-pill {:tone :warning :tab-spaced? false} (count rows)]"
  [{:keys [tone tab-spaced?]
    :or {tone :neutral tab-spaced? true}} & children]
  (let [tones {:danger  ["var(--danger-lightest)"  "var(--danger-dark)"]
               :warning ["var(--warning-lightest)" "var(--warning-text)"]
               :info    ["var(--badge-calc-bg)"    t/blue-700]
               :success ["var(--success-lightest)" "var(--success-dark)"]
               :neutral ["var(--bg-2)"             "var(--fg-3)"]}
        [bg fg] (get tones tone (:neutral tones))
        base-style {:background bg :color fg
                    :font-family t/font-mono :font-size "11px"
                    :font-weight (:medium t/font-weights)
                    :line-height "1.4"
                    :padding "1px 7px"
                    :border-radius (:full t/border-radius)
                    :white-space "nowrap"}]
    (into [:span {:style (cond-> base-style
                           tab-spaced? (assoc :margin-left "6px"))}]
          children)))

(defn status-badge
  "Maps commission/appraisal status to visual style."
  [{:keys [status]}]
  (let [config {"PROJECTED"     {:label "Projetado"     :variant :default}
                "IN_PAYMENT"    {:label "Em pagamento"  :variant :info}
                "SETTLED"       {:label "Quitado"       :variant :success}
                "CANCELLED"     {:label "Cancelado"     :variant :error}
                "DRAFT"         {:label "Rascunho"      :variant :default}
                "CALCULATING"   {:label "Calculando"    :variant :info}
                "VALIDATING"    {:label "Validação"     :variant :info}
                "REVIEWING"     {:label "Revisão"       :variant :warning}
                "APPROVED"      {:label "Aprovado"      :variant :success}
                "LOCKED"        {:label "Fechado"       :variant :default}
                "PENDING"       {:label "Pendente"      :variant :warning}
                "CONTESTED"     {:label "Contestado"    :variant :error}
                "RESOLVED"      {:label "Resolvido"     :variant :success}
                "AUTO_APPROVED" {:label "Auto-aprovado" :variant :success}}
        {:keys [label variant]} (get config status {:label (or status "·") :variant :default})]
    [badge {:variant variant} label]))
