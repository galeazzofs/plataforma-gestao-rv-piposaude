(ns app.views.revops.appraisal-preview
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.views.revops.appraisal-review :as review]
            [app.auth.subs]))

;; Prévia Mensal — read-only "rascunho" of Comissão EV.
;; Runs the real monthly calculator against the financial data already
;; imported for (month, year) and shows the same review breakdown, but the
;; backend rolls everything back: nothing is saved and no apólice is touched.
;; Lets RevOps check a month before locking it, instead of finding out only
;; at apuração close.

(defn- fmt-int [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (.toLocaleString (js/Math.round n) "pt-BR")))))

(def ^:private meses
  ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
   "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(defn- month-options []
  (vec (map-indexed (fn [i m] {:value (str (inc i)) :label m}) meses)))

(defn- month-label [month year]
  (let [m (cond (number? month) month
                (string? month) (js/parseInt month)
                :else nil)]
    (if (and m (<= 1 m 12))
      (str (nth meses (dec m)) "/" year)
      (str "·/" (or year "·")))))

(defn- current-month []
  (inc (.getMonth (js/Date.))))

(defn- year-options []
  (let [cy (.getFullYear (js/Date.))]
    (for [y [(dec cy) cy (inc cy)]]
      {:value (str y) :label (str y)})))

(defn- count-pill [n tone]
  [:span {:style {:background (case tone
                                :danger  "var(--danger-lightest)"
                                :warning "var(--warning-lightest)"
                                :success "var(--success-lightest)"
                                "var(--bg-2)")
                  :color (case tone
                           :danger  "var(--danger-text)"
                           :warning "var(--warning-text)"
                           :success "var(--success-text)"
                           "var(--fg-3)")
                  :font-family "var(--font-mono)" :font-size "11px"
                  :padding "1px 7px" :border-radius "var(--r-pill)"
                  :margin-left "6px"}}
   n])

(defn- tab-button [active-tab k label n tone]
  [:button {:type "button"
            :class (str "tab" (when (= @active-tab k) " active"))
            :role "tab" :aria-selected (str (= @active-tab k))
            :on-click #(reset! active-tab k)}
   label [count-pill n tone]])

(defn- controls [form loading?]
  [:div.card.appraisal-control-card
   [:div.appraisal-control-row
    [:div
     [:div.card-asof "rascunho mensal"]
     [:h3 "Competência da prévia"]
     [:div.card-sub "Use os dados financeiros já importados para validar o mês antes do fechamento."]]
    [:div.appraisal-control-fields
     [inputs/select
      {:label "Mês" :value (:month @form)
       :options (month-options)
       :on-change #(swap! form assoc :month %)}]
     [inputs/select
      {:label "Ano" :value (:year @form)
       :options (year-options)
       :on-change #(swap! form assoc :year %)}]
     [:button.btn.btn-primary
      {:disabled loading?
       :on-click #(rf/dispatch [:revops/run-preview
                                {:month (:month @form) :year (:year @form)}])}
      (if loading?
        "Calculando…"
        [:<> [layout/icon "refresh" {:width 14 :height 14}] " Rodar prévia"])]]]
   [:div.appraisal-facts
    [:span.appraisal-fact
     [layout/icon "calendar" {:width 13 :height 13}]
     (str "Competência " (month-label (:month @form) (:year @form)))]
    [:span.appraisal-fact "somente leitura"]
    [:span.appraisal-fact "não altera apólices"]]])

(defn- kpis [totals]
  [:div.kpi-grid
   [:div.kpi
    [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "comissão total"]
    [:div.kpi-value [:span.currency "R$"]
     (or (fmt-int (:total_commission totals)) "·")]
    [:div.kpi-foot "valor estimado"]]
   [:div.kpi
    [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "NF líquido"]
    [:div.kpi-value [:span.currency "R$"]
     (or (fmt-int (:nf_liquido_total totals)) "·")]
    [:div.kpi-foot "soma das NFs apuradas"]]
   [:div.kpi
    [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs"]
    [:div.kpi-value (str (or (:ev_count totals) 0))]
    [:div.kpi-foot "com comissão no mês"]]
   [:div.kpi
    [:div.kpi-label [layout/icon "doc" {:width 14 :height 14}] "apólices"]
    [:div.kpi-value (str (or (:policy_count totals) 0))]
    [:div.kpi-foot "incluídas na memória"]]
   [:div.kpi
    [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "NFs OK"]
    [:div.kpi-value (str (or (:matched_nf_count totals) 0))]
    [:div.kpi-foot "matcheadas"]]])

(defn- result-view [result active-tab]
  (let [ev-summary  (or (:ev_summary result) [])
        unmatched   (or (:unmatched result) [])
        nao-sup     (or (:nao_suportado result) [])
        finalizadas (or (:apolices_finalizadas result) [])
        missing     (or (:missing_achievements result) [])
        totals      (or (:totals result) {})]
    [:<>
     [:div.callout.-warning {:style {:margin-bottom "16px"}}
      [layout/icon "info" {:width 20 :height 20}]
      [:div {:style {:flex 1}}
       [:strong (str "Rascunho de " (month-label (:month result) (:year result)))]
       [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
        "Números calculados sem salvar comissão, status de apólice ou notificações."]]]

     (when (review/period-empty? totals)
       [review/empty-period-hint (:month result) (:year result)
        (:financial_data_periods result)])

     (when (seq missing)
       [:div.callout.-danger {:style {:margin-bottom "16px"}}
        [layout/icon "alert" {:width 20 :height 20}]
        [:div {:style {:flex 1}}
         [:strong "Atingimentos faltando — apurados como 0%"]
         [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
          "Estes EVs estão sem atingimento usado pela regra do gongo, então "
          "saíram no piso da tabela. Preencha em Atingimento EV antes do fechamento:"]
         [:div {:style {:font-family "var(--font-mono)" :font-size "12px"
                        :color "var(--fg-1)" :margin-top "6px"}}
          (str/join " · " missing)]]])

     [kpis totals]

     [:div.card {:style {:padding 0}}
      [:div {:style {:padding "0 24px"}}
       [:div.tabs {:role "tablist" :aria-label "Visões da prévia"}
        [tab-button active-tab :por-ev "Por EV" (count ev-summary) :neutral]
        [tab-button active-tab :unmatched "Não matcheadas" (count unmatched) :danger]
        [tab-button active-tab :finalizadas "Apólices finalizadas" (count finalizadas) :success]
        [tab-button active-tab :nao-sup "Não suportado" (count nao-sup) :neutral]]]
      [:div {:style {:padding "20px 24px"}}
       (case @active-tab
         :por-ev      [review/por-ev-tab ev-summary]
         :unmatched   [review/nf-table unmatched]
         :finalizadas [review/nf-table finalizadas]
         :nao-sup     [review/nf-table nao-sup])]]]))

(defn page []
  (let [form       (r/atom {:month (str (current-month))
                            :year  (str (.getFullYear (js/Date.)))})
        active-tab (r/atom :por-ev)]
    (fn []
      (let [result   @(rf/subscribe [:revops/preview-result])
            loading? @(rf/subscribe [:revops/preview-loading?])
            error    @(rf/subscribe [:revops/preview-error])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "admin" "prévia mensal"]
          :title "Prévia da competência"
          :subtitle "Rascunho mensal da Comissão EV, sem gravação"}

         [controls form loading?]

         (cond
           loading?
           [:div.card [:div {:style {:padding "48px" :text-align "center"
                                      :color "var(--fg-3)"}} "Calculando prévia…"]]

           error
           [:div.callout.-danger
            [layout/icon "alert" {:width 20 :height 20}]
            [:div {:style {:flex 1}}
             [:strong "Não foi possível gerar a prévia"]
             [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
              error]]]

           (nil? result)
           [:div.card
            [:div.empty {:style {:padding "48px" :text-align "center"}}
             [:div.empty-illus [layout/icon "calendar" {:width 40 :height 40}]]
             [:h4 "Prévia ainda não gerada"]
             [:p {:style {:color "var(--fg-3)"}}
              "A competência selecionada ainda não tem um rascunho calculado nesta sessão."]]]

           :else
           [result-view result active-tab])]))))
