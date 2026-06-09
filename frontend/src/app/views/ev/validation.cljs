(ns app.views.ev.validation
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

;; EV · Validação — list of deals to approve / contest. Each row is an
;; expandable apólice: clicking it drills into the NF breakdown + apuração
;; facts, and the approve/contest actions live both on the row and inside it.

(defn- num [v]
  (cond
    (nil? v) 0
    (number? v) v
    (string? v) (or (js/parseFloat v) 0)
    :else 0))

(defn- fmt-int [v]
  (when (some? v)
    (let [n (num v)]
      (when-not (js/isNaN n) (.toLocaleString (js/Math.round n) "pt-BR")))))

(defn- fmt-money [v]
  (when (some? v)
    (let [n (num v)]
      (when-not (js/isNaN n)
        (.toLocaleString n "pt-BR" #js {:minimumFractionDigits 2
                                        :maximumFractionDigits 2})))))

(defn- fmt-pct [v]
  (when (some? v)
    (let [n (num v)]
      (when-not (js/isNaN n) (.toFixed n 1)))))

(defn- status-badge [status]
  (case status
    "PENDING"       [:span.badge.badge-pending "Pendente"]
    "APPROVED"      [:span.badge.badge-approved "Aprovado"]
    "AUTO_APPROVED" [:span.badge.badge-approved "Auto-aprovado"]
    "CONTESTED"     [:span.badge.badge-contested "Contestado"]
    "RESOLVED"      [:span.badge.badge-approved "Resolvido"]
    [:span.badge.badge-locked (or status "·")]))

;; ── Contest modal ─────────────────────────────────────────

(defn- contest-modal []
  (let [comment (r/atom "")]
    (fn [{:keys [open? on-close on-submit deal-id]}]
      [modal/modal {:open? open? :on-close on-close
                    :title "Contestar negócio" :size :md}
       [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
        [:p {:style {:color "var(--fg-3)" :margin 0 :font-size "13px" :line-height "1.6"}}
         "Descreva o motivo da contestação. Sua mensagem será enviada ao RevOps para análise."]
        [inputs/input
         {:label "Comentário"
          :value @comment
          :placeholder "Ex: O MRR calculado está incorreto porque…"
          :on-change #(reset! comment %)
          :required true}]
        [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
         [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
         [btn/button {:variant :danger
                      :disabled (str/blank? @comment)
                      :on-click #(do (on-submit deal-id @comment)
                                     (reset! comment "")
                                     (on-close))}
          "Contestar"]]]])))

;; ── Row actions (approve / contest) ───────────────────────

(defn- row-actions
  "Aprovar/Contestar buttons. stopPropagation so a click on an action never
  toggles the row open/closed. Disabled + relabelled while a request is in
  flight so a double-click can't re-fire."
  [{:keys [row busy? on-contest]}]
  (when (= (:status row) "PENDING")
    (let [id (:id row)]
      [:div.ev-val-actions
       [:button.btn.btn-primary.btn-sm
        {:disabled busy?
         :on-click (fn [e]
                     (.stopPropagation e)
                     (rf/dispatch [:ev/approve-validation id]))}
        (if busy? "Aprovando…" "Aprovar")]
       [:button.btn.btn-danger.btn-sm
        {:disabled busy?
         :on-click (fn [e]
                     (.stopPropagation e)
                     (on-contest id))}
        "Contestar"]])))

;; ── Expanded apólice detail (NFs + apuração facts) ────────

(defn- deal-detail [row]
  [:div.appraisal-policy-detail.ev-val-detail
   [:div.appraisal-policy-facts
    [:div "Operadora: " (or (:operadora row) "·")]
    [:div "Segmento: " (or (:segment row) "·")]
    [:div "Apólice: " (or (:numero_apolice row) "·")]
    [:div "Meses pagos: " (str (or (:installments_paid row) 0) "/12")]
    [:div "Atingimento: " (str (or (fmt-pct (:achievement_pct row)) "·") "%")]
    [:div "% Comissão: " (str (or (fmt-pct (* 100 (num (:commission_pct row)))) "·") "%")]
    [:div "Gongo: " (or (:closed_date row) "·")]]
   (if (seq (:nfs row))
     [:table.table.appraisal-policy-table
      [:thead [:tr [:th "Data"] [:th "Tipo receita"] [:th.right "NF Líquido"]]]
      [:tbody
       (map-indexed
        (fn [i nf]
          ^{:key i}
          [:tr
           [:td.num.muted (:data_recebimento nf)]
           [:td (:tipo_receita nf)]
           [:td.right.strong-num (str "R$ " (or (fmt-money (:nf_liquido nf)) "·"))]])
        (:nfs row))]
      [:tfoot
       [:tr.appraisal-nf-total-row
        [:td.right.appraisal-nf-total-label {:col-span 2} "Total NF líquido"]
        [:td.right.appraisal-nf-total-value
         (str "R$ " (or (fmt-money (:nf_liquido_total row)) "0,00"))]]]]
     [:div.appraisal-policy-reason.-detail
      "Sem NFs nesta competência — a comissão deste mês vem de outras receitas."])])

;; ── Rows for one deal (summary + optional detail) ─────────

(defn- deal-rows [row {:keys [open-set in-flight toggle on-contest]}]
  (let [id     (:id row)
        open?  (contains? open-set id)
        busy?  (contains? in-flight id)]
    (cond-> [^{:key id}
             [:tr.ev-val-summary
              {:class (when open? "is-open")
               :on-click #(toggle id)}
              [:td.name
               [:button.ev-val-caret
                {:type "button"
                 :aria-expanded (str open?)
                 :aria-label (if open? "Ocultar detalhes" "Ver detalhes")
                 :on-click (fn [e] (.stopPropagation e) (toggle id))}
                [layout/icon "arrow-right" {:width 12 :height 12}]]
               (:client_name row)]
              [:td.muted (or (:benefit_type row) "·")]
              [:td.right.strong-num (str "R$ " (or (fmt-int (:mrr row)) "·"))]
              [:td.right.strong-num (str "R$ " (or (fmt-int (:commission_monthly row)) "·"))]
              [:td [status-badge (:status row)]]
              [:td.right [row-actions {:row row :busy? busy? :on-contest on-contest}]]]]
      open?
      (conj ^{:key (str id "-detail")}
            [:tr.ev-val-detail-row
             [:td {:col-span 6} [deal-detail row]]]))))

;; ── Page ──────────────────────────────────────────────────

(defn validation-page []
  (rf/dispatch [:ev/fetch-validations])
  (let [contest-open?   (r/atom false)
        contest-deal-id (r/atom nil)
        active-tab      (r/atom :pending)
        open-ids        (r/atom #{})]
    (fn []
      (let [validations @(rf/subscribe [:ev/validations])
            loading?    @(rf/subscribe [:ev/validations-loading?])
            in-flight   @(rf/subscribe [:ev/validations-in-flight])
            user        @(rf/subscribe [:auth/current-user])
            route       @(rf/subscribe [:current-route-name])
            rows        (or validations [])
            pending     (filter #(= (:status %) "PENDING") rows)
            approved    (filter #(#{"APPROVED" "AUTO_APPROVED" "RESOLVED"} (:status %)) rows)
            contested   (filter #(= (:status %) "CONTESTED") rows)
            shown (case @active-tab
                    :pending pending
                    :approved approved
                    :contested contested
                    rows)
            total-mrr (reduce + 0 (map #(num (:mrr %)) rows))
            total-comm (reduce + 0 (map #(num (:commission_monthly %)) rows))
            open-contest (fn [id]
                           (reset! contest-deal-id id)
                           (reset! contest-open? true))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "ev" "validação"]
          :title "Validação"
          :subtitle "Revise cada apólice, veja os detalhes e aprove ou conteste"
          :header-actions
          [[:button.btn.btn-primary
            {:disabled (empty? pending)
             :on-click #(doseq [r pending]
                          (rf/dispatch [:ev/approve-validation (:id r)]))}
            [layout/icon "check" {:width 14 :height 14}] "Aprovar todos"]]}

         ;; KPIs
         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "list" {:width 14 :height 14}] "negócios"]
           [:div.kpi-value (str (count rows))]
           [:div.kpi-foot (str (count pending) " pendentes")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "MRR total"]
           [:div.kpi-value [:span.currency "R$"] (fmt-int total-mrr)]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "comissão estimada"]
           [:div.kpi-value [:span.currency "R$"] (fmt-int total-comm)]]]

         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "0 24px"}}
           [:div.tabs {:role "tablist" :aria-label "Status da validação"}
            [:button {:type "button"
                      :class (str "tab" (when (= @active-tab :pending) " active"))
                      :role "tab" :aria-selected (str (= @active-tab :pending))
                      :on-click #(reset! active-tab :pending)}
             "Pendentes "
             [:span {:style {:background "var(--warning-lightest)" :color "var(--warning-text)"
                             :font-family "var(--font-mono)" :font-size "11px"
                             :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
              (count pending)]]
            [:button {:type "button"
                      :class (str "tab" (when (= @active-tab :approved) " active"))
                      :role "tab" :aria-selected (str (= @active-tab :approved))
                      :on-click #(reset! active-tab :approved)}
             "Aprovados " [:span {:style {:background "var(--bg-2)" :color "var(--fg-3)"
                                          :font-family "var(--font-mono)" :font-size "11px"
                                          :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
                           (count approved)]]
            [:button {:type "button"
                      :class (str "tab" (when (= @active-tab :contested) " active"))
                      :role "tab" :aria-selected (str (= @active-tab :contested))
                      :on-click #(reset! active-tab :contested)}
             "Contestados " [:span {:style {:background "var(--danger-lightest)" :color "var(--danger-text)"
                                            :font-family "var(--font-mono)" :font-size "11px"
                                            :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
                             (count contested)]]]]
          [:div.table-wrap
           [:table.table.ev-val-table
            [:thead
             [:tr
              [:th "Cliente"]
              [:th "Benefício"]
              [:th.right "MRR"]
              [:th.right "Comissão/mês"]
              [:th "Status"]
              [:th.right "Ações"]]]
            [:tbody
             (cond
               loading?
               [:tr [:td {:col-span 6 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                     "Carregando…"]]

               (empty? shown)
               [:tr [:td {:col-span 6 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                     "Nenhuma validação"]]

               :else
               (mapcat #(deal-rows % {:open-set @open-ids
                                      :in-flight in-flight
                                      :toggle (fn [id] (swap! open-ids
                                                              (fn [s] (if (contains? s id)
                                                                        (disj s id)
                                                                        (conj s id)))))
                                      :on-contest open-contest})
                       shown))]]]]

         [contest-modal {:open? @contest-open?
                         :on-close #(reset! contest-open? false)
                         :on-submit (fn [id comment]
                                      (rf/dispatch [:ev/contest-validation id comment]))
                         :deal-id @contest-deal-id}]]))))
