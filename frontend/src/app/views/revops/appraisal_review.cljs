(ns app.views.revops.appraisal-review
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Apuração · Revisão (deep view) — KPIs row + tabs (Por EV / NFs órfãs).

(defn- fmt-int [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (.toLocaleString (js/Math.round n) "pt-BR")))))

(defn- fmt-money [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (.toLocaleString n "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2})))))

(defn- fmt-pct [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (.toFixed n 1)))))

(def ^:private meses
  ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
   "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(defn- month-label [month year]
  (let [m (cond (number? month) month
                (string? month) (js/parseInt month)
                :else nil)]
    (if (and m (<= 1 m 12))
      (str (nth meses (dec m)) "/" year)
      (str "·/" (or year "·")))))

(def ^:private status-labels
  {"DRAFT"         "Rascunho"
   "CALCULATING"   "Calculando"
   "VALIDATING"    "Com EVs"
   "LIDER_REVIEW"  "Revisão líder"
   "REVOPS_REVIEW" "Revisão RevOps"
   "LOCKED"        "Fechada"})

(defn- status-label [status]
  (get status-labels status (or status "·")))

(defn- status-class [status]
  (case status
    "DRAFT"         "badge-draft"
    "CALCULATING"   "badge-calc"
    "VALIDATING"    "badge-validating"
    "LIDER_REVIEW"  "badge-review"
    "REVOPS_REVIEW" "badge-review"
    "LOCKED"        "badge-paid"
    "badge-locked"))

(defn- status->badge [status]
  [:span {:class (str "badge " (status-class status))}
   (status-label status)])

(defn- tone-class [tone]
  (when tone (str " -" (name tone))))

(defn- count-pill [n tone]
  [:span {:class (str "appraisal-tab-count" (tone-class tone))}
   n])

(defn- tab-button [active-tab k label n tone]
  [:button {:type "button"
            :class (str "tab" (when (= @active-tab k) " active"))
            :role "tab" :aria-selected (str (= @active-tab k))
            :on-click #(reset! active-tab k)}
   label [count-pill n tone]])

(defn- match-status-label [status]
  (case status
    "MATCHED" "Matcheada"
    "UNMATCHED" "Não matcheada"
    "EXPIRED" "Fora de vigência"
    "UNSUPPORTED_PRODUCT" "Não suportado"
    "APOLICE_FINALIZADA" "Apólice finalizada"
    (or status "·")))

(defn- match-status->badge [status]
  [:span {:class (str "badge "
                      (case status
                        "MATCHED" "badge-approved"
                        "UNMATCHED" "badge-contested"
                        "EXPIRED" "badge-review"
                        "UNSUPPORTED_PRODUCT" "badge-locked"
                        "APOLICE_FINALIZADA" "badge-paid"
                        "badge-review"))}
   (match-status-label status)])

;; ── EV validation status (who approved / who's pending) ───

(defn- validation-status-badge
  "Per-policy EV-validation status badge."
  [status]
  (case status
    "PENDING"       [:span.badge.badge-pending "Pendente EV"]
    "APPROVED"      [:span.badge.badge-approved "Aprovada EV"]
    "AUTO_APPROVED" [:span.badge.badge-approved "Auto-aprovada"]
    "CONTESTED"     [:span.badge.badge-contested "Contestada"]
    "RESOLVED"      [:span.badge.badge-approved "Resolvida"]
    nil))

(defn- validation-ev-badge
  "Per-EV approval-progress badge for the Por EV header."
  [vs]
  (when (and vs (pos? (or (:total vs) 0)))
    (cond
      (pos? (or (:contested vs) 0))
      [:span.badge.badge-contested
       (str (:contested vs) " contestada" (when (> (:contested vs) 1) "s"))]
      (:all_done vs)
      [:span.badge.badge-approved "✓ aprovado"]
      :else
      [:span.badge.badge-pending
       (str (:done vs) "/" (:total vs) " aprovadas")])))

;; ── Conferência por EV (sign-off) — helpers puros ─────────

(defn signoff-status
  "Estado efetivo da conferência de um bloco de EV:
   :done / :changed / :pending / nil (payload sem conferência)."
  [ev]
  (let [s (:signoff ev)]
    (cond
      (nil? s)                nil
      (= "DONE" (:status s))  :done
      (:values_changed s)     :changed
      :else                   :pending)))

(defn signoff-progress
  "{:total n :done m :all-done? bool} a partir do signoff_totals."
  [appraisal]
  (let [{:keys [total done all_done]} (:signoff_totals appraisal)]
    {:total (or total 0) :done (or done 0) :all-done? (boolean all_done)}))

(defn conference-active?
  "A esteira de conferência só aparece durante o CALCULATING (depois vira
   histórico read-only nos badges)."
  [appraisal]
  (and (= "CALCULATING" (:status appraisal))
       (some? (:signoff_totals appraisal))))

(defn sort-evs-for-conference
  "Pendentes (incl. ⚠ valores mudaram) primeiro; alfabético dentro do grupo."
  [evs]
  (sort-by (fn [ev] [(if (= :done (signoff-status ev)) 1 0)
                     (or (:ev_name ev) "")])
           evs))

(defn filter-evs-by-signoff [evs filter-k]
  (case filter-k
    :pendentes  (remove #(= :done (signoff-status %)) evs)
    :conferidos (filter #(= :done (signoff-status %)) evs)
    evs))

(defn release-blocked?
  "true quando o Liberar para EVs deve ficar desabilitado: CALCULATING com
   conferências pendentes. O servidor também bloqueia (defesa em camadas)."
  [appraisal]
  (let [{:keys [total done]} (signoff-progress appraisal)]
    (and (= "CALCULATING" (:status appraisal))
         (pos? total)
         (< done total))))

(defn- lider-gate-callout
  "Shown when a fully-or-partly validated appraisal is held in VALIDATING
  because a required líder hasn't validated their own quarterly appraisal —
  the otherwise-invisible second gate on the advance."
  [appraisal]
  (let [gate (:lider_gate appraisal)]
    (when (and gate (:blocked gate)
               (contains? #{"CALCULATING" "VALIDATING"} (:status appraisal)))
      [:div.callout.-warning
       [layout/icon "clock" {:width 20 :height 20}]
       [:div.appraisal-callout-body
        [:strong "Aguardando validação da liderança"]
        [:div.appraisal-callout-text
         "Mesmo com os EVs validados, a apuração só avança quando cada líder "
         "responsável valida a própria apuração de liderança do trimestre "
         (str "(Q" (:quarter gate) "/" (:year gate) "). Pendentes:")]
        [:div.appraisal-callout-meta
         (str/join " · "
                   (for [l (:pending_leaders gate)]
                     (if (:has_appraisal l)
                       (str (:name l) " — " (or (:own_status l) "pendente"))
                       (str (:name l) " — sem apuração de liderança criada"))))]]])))

(defn period-empty?
  "True when the period has no imported NFs of any match status."
  [totals]
  (zero? (+ (or (:matched_nf_count totals) 0)
            (or (:unmatched_count totals) 0)
            (or (:nao_suportado_count totals) 0)
            (or (:apolices_finalizadas_count totals) 0))))

(defn empty-period-hint
  "Callout shown when the apuração's month has no imported NFs, pointing at the
  months that actually carry financial data (apuração is per-month now)."
  [month year periods]
  (when (seq periods)
    [:div.callout.-warning.appraisal-period-empty-callout
     [layout/icon "info" {:width 20 :height 20}]
     [:div.appraisal-callout-body
      [:strong (str "Nenhuma NF importada para " (month-label month year))]
      [:div.appraisal-callout-text
       "A apuração é mensal: ela só enxerga as NFs cujo recebimento caiu no "
       "mês escolhido. Os dados financeiros que você importou estão nestes "
       "meses. Selecione um deles para apurar:"]
      [:div.appraisal-callout-meta
       (str/join " · "
                 (for [p periods]
                   (str (month-label (:month p) (:year p))
                        " (" (:nf_count p) " NFs)")))]]]))

;; ── NF table for unmatched/nao-suportado ──

(defn nf-table [rows]
  (let [show-finalizada-mes? (boolean (some :apolice_finalizada_mes rows))
        col-span (if show-finalizada-mes? 8 7)]
    [:div.table-wrap.appraisal-nf-table
     [:table.table
      [:thead
       [:tr
        [:th "Cliente"] [:th "Operadora"] [:th "Produto"] [:th "Data"]
        [:th "Tipo receita"] [:th.right "NF Líquido"] [:th "Status"]
        (when show-finalizada-mes? [:th "Ciclo 12/12"])]]
      [:tbody
       (if (empty? rows)
         [:tr [:td.appraisal-empty-cell {:col-span col-span}
               "Nenhuma linha"]]
         (for [r rows]
           ^{:key (or (:id r) (hash r))}
           [:tr
            [:td (:cliente_mae r)]
            [:td.muted (:operadora r)]
            [:td.muted (:produto r)]
            [:td.num.muted (:data_recebimento r)]
            [:td (:tipo_receita r)]
            [:td.right.strong-num (str "R$ " (or (fmt-money (:nf_liquido r)) "·"))]
            [:td [match-status->badge (:match_status r)]]
            (when show-finalizada-mes?
              [:td.num.muted (or (:apolice_finalizada_mes r) "·")])]))]]]))

(defn- export-csv-button [rows filename]
  [:button.btn.btn-secondary.btn-sm
   {:on-click
    (fn []
      (let [headers ["cliente_mae" "operadora" "produto" "data_recebimento"
                     "tipo_receita" "nf_liquido" "match_status"
                     "apolice_finalizada_mes"]
            quote (fn [v] (str "\"" (or v "") "\""))
            line (fn [r] (str/join "," (map #(quote (get r (keyword %))) headers)))
            csv (str/join "\n" (cons (str/join "," headers) (map line rows)))
            blob (js/Blob. #js [csv] #js {:type "text/csv"})
            url (.createObjectURL js/URL blob)
            a (.createElement js/document "a")]
        (set! (.-href a) url)
        (set! (.-download a) filename)
        (.click a)
        (.revokeObjectURL js/URL url)))}
   [layout/icon "download" {:width 12 :height 12}] " Exportar CSV"])

(defn- money-ledger [{:keys [amount nf-total subsidy-total base-total size]}]
  [:div {:class (str "appraisal-money-ledger -" (name (or size :compact)))}
   [:strong.appraisal-money-amount
    (str "R$ " (or (fmt-money amount) "·"))]
   [:div.appraisal-money-breakdown
    [:span "NF líquido"]
    [:b (str "R$ " (or (fmt-money nf-total) "0,00"))]
    (when (pos? (or subsidy-total 0))
      [:<>
       [:span "Subsídio"]
       [:b.appraisal-money-deduction
        (str "-R$ " (or (fmt-money subsidy-total) "0,00"))]])
    (when (some? base-total)
      [:<>
       [:span "Base"]
       [:b (str "R$ " (or (fmt-money base-total) "0,00"))]])]])

(defn- commission-base-line [policy]
  (when (:apurada policy)
    [:div.appraisal-commission-base-line
     [:span "Base antes da comissão"]
     [:b (str "NF R$ " (or (fmt-money (:nf_liquido_total policy)) "0,00"))]
     [:span "-"]
     [:b (str "Subsídio R$ " (or (fmt-money (:subsidio_aplicado policy)) "0,00"))]
     [:span "="]
     [:b (str "R$ " (or (fmt-money (:base_comissionavel policy)) "0,00"))]]))

;; ── Policy block (one per Policy under an EV) ─────────────

(defn- policy-block []
  (let [open? (r/atom false)]
    (fn [policy]
      (let [apurada? (:apurada policy)]
        [:div {:class (str "appraisal-policy-row"
                           (when-not apurada? " -not-apurada"))}
         [:button.appraisal-review-row-button.appraisal-policy-button
          {:type "button"
           :aria-expanded (str @open?)
           :on-click #(swap! open? not)}
          [:div.appraisal-row-main
           [:div.appraisal-policy-title
            [:strong (or (:client_name policy) "·")]
            (when-not apurada?
              [:span.badge.badge-locked "Não apurada"])
            (when apurada?
              [validation-status-badge (:validation_status policy)])]
           [:span.appraisal-policy-meta
            (str (or (:operadora policy) "·") " · "
                 (or (:produto policy) "·") " · "
                 (or (:segment policy) "·"))]]
          (if apurada?
            [money-ledger {:amount (:subtotal policy)
                           :nf-total (:nf_liquido_total policy)
                           :subsidy-total (:subsidio_aplicado policy)
                           :base-total (:base_comissionavel policy)
                           :size :policy}]
            [:div.appraisal-policy-reason
             (or (:reason policy) "Não apurada")])]
         (when @open?
           [:div.appraisal-policy-detail
            [:div.appraisal-policy-facts
             [:div "Meses pagos: " (str (or (:installments_paid policy) 0) "/12")]
             [:div.muted "Início vigência (ref. HubSpot, não usada no cálculo): "
              (or (:first_payment_real policy) "·")]
             [:div "Gongo: " (or (:closed_date policy) "·")]
             (when apurada?
               [:div "Atingimento: " (str (or (fmt-pct (:achievement_used_pct policy)) "·") "%")])
             (when apurada?
               [:div "% Comissão: " (str (or (fmt-pct (* 100 (or (:commission_pct policy) 0))) "·") "%")])]
            [commission-base-line policy]
            (if apurada?
              [:table.table.appraisal-policy-table
               [:thead [:tr [:th "Data"] [:th "Tipo"] [:th.right "NF Líquido"]]]
               [:tbody
                (if (empty? (:nfs policy))
                  [:tr [:td.appraisal-empty-cell {:col-span 3}
                        "·"]]
                  (for [nf (:nfs policy)]
                    ^{:key (or (:id nf) (hash nf))}
                    [:tr
                     [:td.num.muted (:data_recebimento nf)]
                     [:td (:tipo_receita nf)]
                     [:td.right.strong-num (str "R$ " (or (fmt-money (:nf_liquido nf)) "·"))]]))]
               (when (seq (:nfs policy))
                  [:tfoot
                   [:tr.appraisal-nf-total-row
                    [:td.right.appraisal-nf-total-label {:col-span 2} "Total NF líquido"]
                    [:td.right.appraisal-nf-total-value
                     (str "R$ " (or (fmt-money (:nf_liquido_total policy)) "·"))]]])]
              [:div.appraisal-policy-reason.-detail
               (str "Sem comissão nesta competência: "
                    (or (:reason policy) "não apurada") ".")])])]))))

;; ── EV row ────────────────────────────────────────────────

(defn- ev-row []
  (let [open? (r/atom false)
        apurada-filter (r/atom :apuradas)]
    (fn [ev tipo-filter operadora-filter]
      (let [filter-nfs (fn [nfs]
                         (if (or (nil? tipo-filter) (= "Todos" tipo-filter))
                           nfs
                           (filter #(= (:tipo_receita %) tipo-filter) nfs)))
            base (->> (:policies ev)
                      (filter (fn [p]
                                (or (nil? operadora-filter)
                                    (= "Todas" operadora-filter)
                                    (= (:operadora p) operadora-filter))))
                      (map (fn [p] (update p :nfs filter-nfs))))
            apuradas     (filter :apurada base)
            nao-apuradas (remove :apurada base)
            visible (case @apurada-filter
                      :apuradas     apuradas
                      :nao-apuradas nao-apuradas
                      base)
            nao-count (or (:nao_apuradas_count ev) (count nao-apuradas))]
        [:div.appraisal-ev-row
         [:button.appraisal-review-row-button.appraisal-ev-button
          {:type "button"
           :aria-expanded (str @open?)
           :on-click #(swap! open? not)}
          [:div.appraisal-row-main
           [:div.name
            (:ev_name ev)
            (when (:ev_left_company ev)
              [:span.badge.badge-review
               "Saiu"])
            [validation-ev-badge (:validation_status ev)]]
           [:div.appraisal-ev-meta
            (str (:policies_count ev) " apuradas · "
                 (when (pos? nao-count) (str nao-count " não apuradas · "))
                 (:nf_count ev) " NFs · atingimento "
                 (or (fmt-pct (:achievement_pct ev)) "·") "%")]]
          [money-ledger {:amount (:total_commission ev)
                         :nf-total (:nf_liquido_total ev)
                         :subsidy-total (:subsidio_aplicado_total ev)
                         :base-total (:base_comissionavel_total ev)
                         :size :ev}]]
         (when @open?
           [:div.appraisal-ev-detail
            [:div.filter-row.appraisal-subfilter-row
             {:role "group" :aria-label "Filtro de apuração"}
             (for [[k label cnt] [[:apuradas "Apuradas" (count apuradas)]
                                  [:nao-apuradas "Não apuradas" (count nao-apuradas)]
                                  [:todas "Todas" (count base)]]]
               ^{:key k}
               [:button {:type "button"
                         :class (str "chip" (when (= k @apurada-filter) " active"))
                         :aria-pressed (str (= k @apurada-filter))
                         :on-click #(reset! apurada-filter k)}
                (str label " (" cnt ")")])]
            (if (empty? visible)
              [:div.appraisal-empty-panel
               "Nenhuma apólice neste filtro"]
              (for [p visible]
                ^{:key (:policy_id p)} [policy-block p]))])]))))

;; ── Por EV tab ────────────────────────────────────────────

(defn por-ev-tab []
  (let [tipo-filter (r/atom "Todos")
        op-filter   (r/atom "Todas")]
    (fn [ev-summary]
      (let [all-ops (->> ev-summary
                         (mapcat :policies)
                         (map :operadora)
                         (remove nil?)
                         distinct sort)]
        [:div
         [:div.appraisal-filter-band
          [:div.appraisal-filter-group
           [:div.appraisal-filter-label "receita"]
           [:div.filter-row.appraisal-filter-row
            {:role "group" :aria-label "Filtro por tipo de receita"}
            (for [t ["Todos" "Comissão" "Fee por Vida" "Premiação" "Patrocínio - Eventos" "Agenciamento"]]
              ^{:key t}
              [:button {:type "button"
                        :class (str "chip" (when (= t @tipo-filter) " active"))
                        :aria-pressed (str (= t @tipo-filter))
                        :on-click #(reset! tipo-filter t)}
               t])]]
          [:div.appraisal-filter-group.-wide
           [:div.appraisal-filter-label "operadora"]
           [:div.filter-row.appraisal-filter-row
            {:role "group" :aria-label "Filtro por operadora"}
            [:button {:type "button"
                      :class (str "chip" (when (= "Todas" @op-filter) " active"))
                      :aria-pressed (str (= "Todas" @op-filter))
                      :on-click #(reset! op-filter "Todas")} "Todas"]
            (for [o all-ops]
              ^{:key o}
              [:button {:type "button"
                        :class (str "chip" (when (= o @op-filter) " active"))
                        :aria-pressed (str (= o @op-filter))
                        :on-click #(reset! op-filter o)}
               o])]]]
         (if (empty? ev-summary)
           [:div.appraisal-empty-panel.-large
            "Nenhum EV com comissão calculada"]
           [:div.appraisal-ev-list
            (for [ev ev-summary]
              ^{:key (:ev_id ev)}
              [ev-row ev @tipo-filter @op-filter])])]))))

;; ── Monthly review summary ────────────────────────────────

(defn- brief-item [{:keys [label value tone]}]
  [:div {:class (str "appraisal-brief-item"
                     (when tone (str " -" (name tone))))}
   [:span.appraisal-brief-label label]
   [:strong value]])

(defn- review-brief [appraisal totals unmatched finalizadas nao-sup]
  [:div.card.appraisal-review-brief
   [:div.appraisal-brief-main
    [:div.appraisal-brief-label "competência mensal"]
    [:div.appraisal-brief-title (month-label (:month appraisal) (:year appraisal))]
    [status->badge (:status appraisal)]
    [:div.card-sub "Resumo operacional antes de liberar ou fechar a Comissão EV."]]
   [:div.appraisal-brief-grid
    [brief-item {:label "NFs OK"
                 :value (str (or (:matched_nf_count totals) 0))
                 :tone :success}]
    [brief-item {:label "não matcheadas"
                 :value (str (count unmatched))
                 :tone :danger}]
    [brief-item {:label "finalizadas / não suportado"
                 :value (str (+ (count finalizadas) (count nao-sup)))}]
    (let [vt (:validation_totals appraisal)]
      (when (and vt (pos? (or (:total vt) 0)))
        [brief-item {:label "validações aprovadas"
                     :value (str (:done vt) "/" (:total vt)
                                 (when (pos? (or (:pending vt) 0))
                                   (str " · " (:pending vt) " pend.")))
                     :tone (cond (pos? (or (:contested vt) 0)) :danger
                                 (:all_done vt) :success
                                 :else nil)}]))]])

;; ── Contestation panel (issue #36) ────────────────────────

(defn- contestation-panel [appraisal user]
  (let [contest-open? (r/atom false)
        contest-text  (r/atom "")
        resolve-text  (r/atom "")]
    (fn [appraisal user]
      (let [id        (:id appraisal)
            status    (:status appraisal)
            has?      (:has_contestation appraisal)
            note      (:contestation_note appraisal)
            res-note  (:resolution_note appraisal)
            role      (:role user)
            admin?    (= role "ADMIN")
            can-contest? (and (not has?) (= status "VALIDATING"))]
        (cond
          ;; Open contestation — show note + resolution form for admins
          has?
          [:div.callout.-danger
           [layout/icon "alert" {:width 20 :height 20}]
           [:div.appraisal-callout-body
            [:strong "Contestação aberta"]
            [:div.appraisal-callout-text.-pre
             (or note "·")]
            (when admin?
              [:div.appraisal-contestation-form
               [:textarea
                {:value @resolve-text
                 :placeholder "Devolutiva (obrigatório). Descreva como o problema foi resolvido."
                 :on-change #(reset! resolve-text (-> % .-target .-value))
                 :rows 3
                 :class "field-input appraisal-textarea"}]
               [:div.appraisal-form-actions
                [:button.btn.btn-primary.btn-sm
                 {:disabled (clojure.string/blank? @resolve-text)
                  :on-click (fn []
                              (rf/dispatch [:revops/resolve-appraisal-contestation
                                            id @resolve-text])
                              (reset! resolve-text ""))}
                 "Resolver e devolver para validação"]]])]]

          ;; Resolution closed — small acknowledgement
          (and (not has?) res-note)
          [:div.callout.-success
           [layout/icon "check" {:width 20 :height 20}]
           [:div.appraisal-callout-body
            [:strong "Contestação resolvida"]
            [:div.appraisal-callout-text.-pre
             res-note]]]

          ;; Can contest — show button + textarea (toggled)
          can-contest?
          [:div.callout.-neutral
           [layout/icon "info" {:width 20 :height 20}]
           [:div.appraisal-callout-body
            [:strong "Contestar valor"]
            [:div.appraisal-callout-text
             "Discordou do valor calculado? Abra uma contestação. A "
             "apuração vai direto para revisão do RevOps."]
            (when @contest-open?
              [:div.appraisal-contestation-form
               [:textarea
                {:value @contest-text
                 :placeholder "Motivo da contestação (obrigatório)"
                 :on-change #(reset! contest-text (-> % .-target .-value))
                 :rows 3
                 :class "field-input appraisal-textarea"}]
               [:div.appraisal-form-actions
                [:button.btn.btn-primary.btn-sm
                 {:disabled (clojure.string/blank? @contest-text)
                  :on-click (fn []
                              (rf/dispatch [:revops/contest-appraisal
                                            id @contest-text])
                              (reset! contest-open? false)
                              (reset! contest-text ""))}
                 "Confirmar contestação"]
                [:button.btn.btn-secondary.btn-sm
                 {:on-click #(do (reset! contest-open? false)
                                 (reset! contest-text ""))}
                 "Cancelar"]]])]
           (when-not @contest-open?
             [:button.btn.btn-secondary.btn-sm
              {:on-click #(reset! contest-open? true)}
              "Contestar"])]

          :else nil)))))

;; ── Page ──────────────────────────────────────────────────

(defn appraisal-review-page []
  (let [route @(rf/subscribe [:current-route])
        appraisal-id (get-in route [:path-params :id])
        active-tab (r/atom :por-ev)]
    (when appraisal-id
      (rf/dispatch [:revops/fetch-appraisal-detail appraisal-id])
      (rf/dispatch [:revops/fetch-appraisals]))
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            appraisal (first (filter #(= (str (:id %)) (str appraisal-id))
                                     (or appraisals [])))
            ev-summary (or (:ev_summary appraisal) [])
            unmatched  (or (:unmatched appraisal) [])
            nao-sup    (or (:nao_suportado appraisal) [])
            apolices-finalizadas (or (:apolices_finalizadas appraisal) [])
            totals     (or (:totals appraisal) {})
            user       @(rf/subscribe [:auth/current-user])
            route-name @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:current-route route-name :user user
          :crumbs ["plataforma rv" "admin" "apurações" (month-label (:month appraisal) (:year appraisal))]
          :title (str "Revisão · " (month-label (:month appraisal) (:year appraisal)))
          :subtitle (if (:status appraisal)
                      (str "Competência mensal · " (status-label (:status appraisal)))
                      "Competência mensal")
          :header-actions
          ;; State-aware: each status shows only the actions that make sense
          ;; there, so REVOPS_REVIEW gets a "Fechar apuração" and never the
          ;; stale "Liberar para EVs".
          (let [st (:status appraisal)]
            (cond-> [[:button.btn.btn-secondary
                      {:on-click #(rf/dispatch [:navigate :revops/appraisal])}
                      "← Voltar"]]
              (contains? #{"CALCULATING" "VALIDATING" "LIDER_REVIEW" "REVOPS_REVIEW"} st)
              (conj [:button.btn.btn-secondary
                     {:on-click #(rf/dispatch [:revops/recalculate-appraisal appraisal-id])}
                     [layout/icon "refresh" {:width 14 :height 14}] "Recalcular"])

              (= st "CALCULATING")
              (conj [:button.btn.btn-primary
                     {:on-click #(rf/dispatch [:revops/release-to-validation appraisal-id])}
                     [layout/icon "check" {:width 14 :height 14}] "Liberar para EVs"])

              (= st "LIDER_REVIEW")
              (conj [:button.btn.btn-primary
                     {:on-click #(rf/dispatch [:revops/advance-to-revops appraisal-id])}
                     [layout/icon "check" {:width 14 :height 14}] "Avançar para RevOps"])

              (= st "REVOPS_REVIEW")
              (conj [:button.btn.btn-primary
                     {:on-click #(rf/dispatch [:revops/lock-appraisal appraisal-id])}
                     [layout/icon "lock" {:width 14 :height 14}] "Fechar apuração"])))}

         ;; Contestation panel (issue #36)
         [contestation-panel appraisal user]

         ;; Mês sem NFs importadas — aponta os meses que têm dados
         (when (period-empty? totals)
           [empty-period-hint (:month appraisal) (:year appraisal)
            (:financial_data_periods appraisal)])

         ;; Atingimentos faltando — apurados como 0% (não bloqueia a apuração)
         (when-let [missing (seq (:missing_achievements appraisal))]
           [:div.callout.-warning
            [layout/icon "alert" {:width 20 :height 20}]
            [:div.appraisal-callout-body
             [:strong "Atingimentos faltando, apurados como 0%"]
             [:div.appraisal-callout-text
              "Estes EVs estão sem atingimento usado pela regra do gongo e "
              "saíram no piso da tabela. Preencha em Atingimento EV e recalcule:"]
             [:div.appraisal-callout-meta
              (str/join " · " missing)]]])

         ;; Travada esperando a liderança validar own (segundo gate, invisível)
         [lider-gate-callout appraisal]

         [review-brief appraisal totals unmatched apolices-finalizadas nao-sup]

         ;; KPIs row
         [:div.kpi-grid.appraisal-review-kpis
          [:div.kpi.appraisal-review-money-kpi
           [:div.split-numerics
            [:div.col
             [:div.lab "comissão total"]
             [:div.num [:span.currency "R$"]
              (or (fmt-int (:total_commission totals)) "·")]
             [:div.kpi-foot "valor da competência"]]
            [:div.rule]
            [:div.col
             [:div.lab "NF líquido"]
             [:div.num [:span.currency "R$"]
              (or (fmt-int (:nf_liquido_total totals)) "·")]
             [:div.kpi-foot "NFs apuradas"]]]]
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs"]
           [:div.kpi-value (str (or (:ev_count totals) 0))]
           [:div.kpi-foot "com comissão"]]
          [:div.kpi
           [:div.kpi-label [layout/icon "doc" {:width 14 :height 14}] "apólices"]
           [:div.kpi-value (str (or (:policy_count totals) 0))]
           [:div.kpi-foot "na memória"]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "NFs OK"]
           [:div.kpi-value (str (or (:matched_nf_count totals) 0))]
           [:div.kpi-foot "matcheadas"]]]

         [:div.appraisal-review-workspace
          [:div.appraisal-tabs-bar
           [:div.tabs.appraisal-review-tabs
            {:role "tablist" :aria-label "Visões de apuração"}
            [tab-button active-tab :por-ev "Por EV" (count ev-summary) :neutral]
            [tab-button active-tab :unmatched "Não matcheadas" (count unmatched) :danger]
            [tab-button active-tab :apolices-finalizadas "Apólices finalizadas" (count apolices-finalizadas) :success]
            [tab-button active-tab :nao-sup "Não suportado" (count nao-sup) :neutral]]]
          [:div.appraisal-review-content
           (case @active-tab
             :por-ev    [por-ev-tab ev-summary]
             :unmatched [:<>
                         [:div.appraisal-table-toolbar
                          [export-csv-button unmatched "nao-matcheadas.csv"]]
                         [nf-table unmatched]]
             :apolices-finalizadas [:<>
                                     [:div.appraisal-table-toolbar
                                      [export-csv-button apolices-finalizadas "apolices-finalizadas.csv"]]
                                     [nf-table apolices-finalizadas]]
             :nao-sup   [:<>
                         [:p.appraisal-table-note
                          "Linhas com produto não suportado pelo modelo (Mental, Fitness)."]
                         [nf-table nao-sup]])]]]))))
