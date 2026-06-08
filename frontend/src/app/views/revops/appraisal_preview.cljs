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
  [:div.card {:style {:padding "18px 20px" :margin-bottom "16px"}}
   [:div {:style {:display "flex" :align-items "flex-end" :gap "12px"
                  :flex-wrap "wrap"}}
    [:div {:style {:min-width "120px"}}
     [inputs/select
      {:label "Mês" :value (:month @form)
       :options (month-options)
       :on-change #(swap! form assoc :month %)}]]
    [:div {:style {:min-width "120px"}}
     [inputs/select
      {:label "Ano" :value (:year @form)
       :options (year-options)
       :on-change #(swap! form assoc :year %)}]]
    [:button.btn.btn-primary
     {:disabled loading?
      :on-click #(rf/dispatch [:revops/run-preview
                               {:month (:month @form) :year (:year @form)}])}
     (if loading?
       "Calculando…"
       [:<> [layout/icon "refresh" {:width 14 :height 14}] " Rodar prévia"])]]
   [:div.muted {:style {:font-size "12px" :margin-top "10px" :max-width "640px"}}
    "A prévia apura só o mês escolhido com os dados já importados. "
    "Nada é gravado: nenhuma comissão final, nenhuma mudança em apólices "
    "(relógio de 12 meses, status, primeiro mês de comissão) e ninguém é "
    "notificado. Para apurar de verdade, use o fluxo da apuração."]])

(defn- kpis [totals]
  [:div.kpi-grid
   [:div.kpi
    [:div.kpi-label "comissão total"]
    [:div.kpi-value [:span.currency "R$"]
     (or (fmt-int (:total_commission totals)) "·")]]
   [:div.kpi
    [:div.kpi-label "EVs"]
    [:div.kpi-value (str (or (:ev_count totals) 0))]]
   [:div.kpi
    [:div.kpi-label "apólices"]
    [:div.kpi-value (str (or (:policy_count totals) 0))]]
   [:div.kpi
    [:div.kpi-label "NFs OK"]
    [:div.kpi-value (str (or (:matched_nf_count totals) 0))]]])

(defn- result-view [result active-tab]
  (let [ev-summary  (or (:ev_summary result) [])
        unmatched   (or (:unmatched result) [])
        expired     (or (:expired result) [])
        nao-sup     (or (:nao_suportado result) [])
        finalizadas (or (:apolices_finalizadas result) [])
        missing     (or (:missing_achievements result) [])
        totals      (or (:totals result) {})]
    [:<>
     [:div.callout {:style {:border-left "3px solid var(--warning-default)"
                            :margin-bottom "16px"}}
      [layout/icon "info" {:width 20 :height 20}]
      [:div {:style {:flex 1}}
       [:strong (str "Rascunho · " (month-label (:month result) (:year result)))]
       [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
        "Estes números não foram salvos. Reflete a apuração com os dados "
        "importados até agora."]]]

     (when (review/period-empty? totals)
       [review/empty-period-hint (:month result) (:year result)
        (:financial_data_periods result)])

     (when (seq missing)
       [:div.callout {:style {:border-left "3px solid var(--danger-default)"
                              :margin-bottom "16px"}}
        [layout/icon "alert" {:width 20 :height 20}]
        [:div {:style {:flex 1}}
         [:strong "Atingimentos faltando — apurados como 0%"]
         [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
          "Estes EVs estão sem atingimento no trimestre da venda (gongo), "
          "então saíram no piso da tabela. Preencha em Atingimento EV antes "
          "da apuração de verdade:"]
         [:div {:style {:font-family "var(--font-mono)" :font-size "12px"
                        :color "var(--fg-1)" :margin-top "6px"}}
          (str/join " · " missing)]]])

     [kpis totals]

     [:div.card {:style {:padding 0}}
      [:div {:style {:padding "0 24px"}}
       [:div.tabs {:role "tablist" :aria-label "Visões da prévia"}
        [tab-button active-tab :por-ev "Por EV" (count ev-summary) :neutral]
        [tab-button active-tab :unmatched "Não matcheadas" (count unmatched) :danger]
        [tab-button active-tab :expired "Fora de vigência" (count expired) :warning]
        [tab-button active-tab :finalizadas "Apólices finalizadas" (count finalizadas) :success]
        [tab-button active-tab :nao-sup "Não suportado" (count nao-sup) :neutral]]]
      [:div {:style {:padding "20px 24px"}}
       (case @active-tab
         :por-ev      [review/por-ev-tab ev-summary]
         :unmatched   [review/nf-table unmatched]
         :expired     [review/nf-table expired]
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
          :title "Prévia Mensal"
          :subtitle "Rascunho da Comissão EV com os dados já importados — sem salvar nada"}

         [controls form loading?]

         (cond
           loading?
           [:div.card [:div {:style {:padding "48px" :text-align "center"
                                      :color "var(--fg-3)"}} "Calculando prévia…"]]

           error
           [:div.callout {:style {:border-left "3px solid var(--danger-default)"}}
            [layout/icon "alert" {:width 20 :height 20}]
            [:div {:style {:flex 1}}
             [:strong "Não foi possível gerar a prévia"]
             [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
              error]]]

           (nil? result)
           [:div.card
            [:div.empty {:style {:padding "48px" :text-align "center"}}
             [:h4 "Nenhuma prévia ainda"]
             [:p {:style {:color "var(--fg-3)"}}
              "Escolha o mês e clique em “Rodar prévia” para ver como a "
              "Comissão EV está com os dados importados até agora."]]]

           :else
           [result-view result active-tab])]))))
