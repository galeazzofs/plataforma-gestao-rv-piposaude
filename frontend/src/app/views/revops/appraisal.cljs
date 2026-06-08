(ns app.views.revops.appraisal
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

;; Apuração EV mensal — cockpit de competências, prévia e fechamento.

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(def ^:private meses
  ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
   "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(def ^:private meses-curtos
  ["Jan" "Fev" "Mar" "Abr" "Mai" "Jun" "Jul" "Ago" "Set" "Out" "Nov" "Dez"])

(defn- safe-int [v]
  (cond
    (number? v) v
    (string? v) (let [n (js/parseInt v 10)]
                  (when-not (js/isNaN n) n))
    :else nil))

(defn- month-options []
  (vec (map-indexed (fn [i m] {:value (str (inc i)) :label m}) meses)))

(defn- month-label [month year]
  (let [m (safe-int month)]
    (if (and m (<= 1 m 12))
      (str (nth meses (dec m)) "/" year)
      (str "·/" (or year "·")))))

(defn- month-short [month]
  (let [m (safe-int month)]
    (if (and m (<= 1 m 12))
      (nth meses-curtos (dec m))
      "·")))

(defn- current-month []
  (inc (.getMonth (js/Date.))))

(defn- current-year []
  (.getFullYear (js/Date.)))

(defn- year-options []
  (let [cy (current-year)]
    (vec (for [y [(dec cy) cy (inc cy)]]
           {:value (str y) :label (str y)}))))

(defn- available-year-options [appraisals]
  (->> (concat [(current-year)] (map :year appraisals))
       (map safe-int)
       (remove nil?)
       distinct
       (sort >)
       (mapv (fn [y] {:value (str y) :label (str y)}))))

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

(def ^:private steps
  ["DRAFT" "CALCULATING" "VALIDATING" "LIDER_REVIEW" "REVOPS_REVIEW" "LOCKED"])
(def ^:private step-labels
  {"DRAFT"         "Rascunho"
   "CALCULATING"   "Calculando"
   "VALIDATING"    "Com EVs"
   "LIDER_REVIEW"  "Líder"
   "REVOPS_REVIEW" "RevOps"
   "LOCKED"        "Fechada"})

(defn- next-action-copy [status]
  (case status
    "DRAFT"
    {:title "Calcular competência"
     :body "Rode a apuração mensal para montar a memória de cálculo dos EVs."}

    "CALCULATING"
    {:title "Abrir revisão"
     :body "Confira matches, valores e exceções antes de liberar a validação."}

    "LIDER_REVIEW"
    {:title "Revisão de liderança"
     :body "Acompanhe ajustes dos líderes e mantenha as exceções visíveis."}

    "REVOPS_REVIEW"
    {:title "Resolver pendências"
     :body "Trate contestações ou ajustes antes de devolver para os EVs."}

    "VALIDATING"
    {:title "Acompanhar EVs"
     :body "A competência já está disponível para validação dos EVs."}

    "LOCKED"
    {:title "Competência fechada"
     :body "A memória fica disponível para consulta e auditoria."}

    {:title "Revisar competência"
     :body "Abra a memória de cálculo para ver o estado atual."}))

(defn- stepper [current]
  (let [idx (max 0 (.indexOf (clj->js steps) (or current "DRAFT")))]
    [:div.stepper
     (for [[i s] (map-indexed vector steps)
           :let [done?    (< i idx)
                 current? (= i idx)]]
       ^{:key s}
       [:<>
        [:div.stepper-stack
         [:div {:class (str "step" (cond done? " done" current? " current"))}
          [:div.step-dot
           (if done?
             [:svg {:style {:width "13px" :height "13px" :color "#fff"} :aria-hidden true}
              [:use {:href "#i-check"}]]
             (str (inc i)))]]
         [:div.step-label
          {:style (cond done?    {:color "var(--fg-1)"}
                        current? {:color "var(--fg-1)" :font-weight 600})}
          (step-labels s)]]
        (when (< i (dec (count steps)))
          [:div.step-line
           {:style (when (or done? (and current? (>= i (dec idx))))
                     {:background "var(--success-dark)"})}])])]))

(defn- new-appraisal-modal [_]
  (let [form (r/atom {:month (str (current-month))
                      :year  (str (current-year))})]
    (fn [{:keys [open? on-close]}]
      [modal/modal {:open? open? :on-close on-close :title "Nova competência mensal" :size :sm}
       [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
        [inputs/select
         {:label "Mês da competência" :value (:month @form)
          :options (month-options)
          :on-change #(swap! form assoc :month %)}]
        [inputs/select
         {:label "Ano" :value (:year @form)
          :options (year-options)
          :on-change #(swap! form assoc :year %)}]
        [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
         [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
         [btn/button {:variant :primary
                      :on-click (fn []
                                  (rf/dispatch [:revops/create-appraisal @form])
                                  (on-close))}
          "Criar competência"]]]])))

(defn- metric [{:keys [label value tone]}]
  [:div.appraisal-metric
   [:div.lab label]
   [:div {:class (str "num" (when tone (str " -" (name tone))))}
    value]])

(defn- active-card [active on-new]
  (if-not active
    [:div.card
     [:div.card-head
      [:div
       [:div.card-asof "competência mensal"]
       [:h2 {:style {:font-family "var(--font-display)" :font-weight 600
                     :font-size "24px" :letter-spacing 0 :margin-top "2px"}}
        "Nenhuma competência aberta"]
       [:div.card-sub "Crie a competência do mês quando os dados financeiros estiverem importados."]]
      [:div.card-actions
       [:button.btn.btn-secondary
        {:on-click #(rf/dispatch [:navigate :revops/appraisal-preview])}
        [layout/icon "trend" {:width 14 :height 14}] "Prévia"]
       [:button.btn.btn-primary
        {:on-click on-new}
        [layout/icon "plus" {:width 14 :height 14}] "Criar"]]]]
    (let [period (month-label (:month active) (:year active))
          status (:status active)
          next-copy (next-action-copy status)]
      [:div.card
       [:div.card-head
        [:div
         [:div.card-asof "competência em aberto"]
         [:h2 {:style {:font-family "var(--font-display)" :font-weight 600
                       :font-size "24px" :letter-spacing 0 :margin-top "2px"}}
          period]
         [:div.card-sub (str "Fluxo mensal da Comissão EV · " (status-label status))]]
        [:div.card-actions
         [status->badge status]
         [:button.btn.btn-primary.btn-sm
          {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id (:id active)}]])}
          "Abrir revisão" [layout/icon "arrow-right" {:width 12 :height 12}]]]]
       [:div.appraisal-active-main
        [stepper status]
        [:div.appraisal-next-box
         [:div.lab "próxima ação"]
         [:strong (:title next-copy)]
         [:span (:body next-copy)]]]
       [:div.appraisal-metric-strip
        [metric {:label "EVs apurados"
                 :value (str (or (:ev_count active) "·"))}]
        [metric {:label "comissão total"
                 :value (if-let [amt (fmt-int (:total_amount active))] (str "R$ " amt) "·")}]
        [metric {:label "contestações"
                 :value (str (or (:contestation_count active) "0"))
                 :tone :warning}]
        [metric {:label "dias para fechar"
                 :value (str (or (:days_remaining active) "·"))}]]])))

(defn- appraisal-for-month [appraisals year month]
  (first (filter #(and (= (safe-int (:year %)) year)
                       (= (safe-int (:month %)) month))
                 appraisals)))

(defn- monthly-cell [appraisals active-id year month]
  (let [a       (appraisal-for-month appraisals year month)
        locked? (= "LOCKED" (:status a))
        active? (= active-id (:id a))
        classes (str "appraisal-period-cell"
                     (when a " has-data")
                     (when active? " is-active")
                     (when locked? " is-locked")
                     (when-not a " is-empty"))]
    (if a
      [:button {:type "button"
                :class classes
                :on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id (:id a)}]])}
       [:span.appraisal-period-month (month-short month)]
       [:span.appraisal-period-status (status-label (:status a))]
       [:span.appraisal-period-total
        (if-let [amt (fmt-int (:total_amount a))]
          (str "R$ " amt)
          "sem total")]]
      [:div {:class classes}
       [:span.appraisal-period-month (month-short month)]
       [:span.appraisal-period-status "Sem apuração"]
       [:span.appraisal-period-total "prévia disponível"]])))

(defn- monthly-rail [appraisals active focus-year year-options on-year-change]
  [:div.card.appraisal-period-card
   [:div.appraisal-period-head
    [:div.appraisal-period-title
     [:h3 "Competências do ano"]
     [:div.card-sub "Acesso rápido às apurações mensais dos EVs."]]
    [:div {:style {:width "132px"}}
     [inputs/select
      {:label "Ano" :value (str focus-year)
       :options year-options
       :on-change on-year-change}]]]
   [:div.appraisal-period-grid
    (for [month (range 1 13)]
      ^{:key (str focus-year "-" month)}
      [monthly-cell appraisals (:id active) focus-year month])]])

(defn- delete-btn [id]
  [:button.btn.btn-danger.btn-sm
   {:on-click (fn [e]
                (.stopPropagation e)
                (when (js/confirm "Tem certeza? Isso vai apagar a apuração e resetar todos os matches de NFs.")
                  (rf/dispatch [:revops/delete-appraisal id])))}
   "Excluir"])

(defn- step-actions [{:keys [status id] :as _row}]
  (case status
    "DRAFT"
    [:<>
     [:button.btn.btn-primary.btn-sm
      {:on-click #(rf/dispatch [:revops/run-appraisal id])}
      "Calcular"]
     [delete-btn id]]

    "CALCULATING"
    [:<>
     [:button.btn.btn-primary.btn-sm
      {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
      "Abrir revisão"]
     [delete-btn id]]

    "LIDER_REVIEW"
    [:<>
     [:button.btn.btn-primary.btn-sm
      {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
      "Abrir revisão"]
     [delete-btn id]]

    "REVOPS_REVIEW"
    [:<>
     [:button.btn.btn-primary.btn-sm
      {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
      "Abrir revisão"]
     [delete-btn id]]

    "VALIDATING"
    [:button.btn.btn-secondary.btn-sm
     {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
     "Acompanhar EVs"]

    "LOCKED"
    [:<>
     [:button.btn.btn-ghost.btn-sm
      {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
      "Ver memória"]
     [delete-btn id]]

    [:button.btn.btn-ghost.btn-sm
     {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
     "Ver"]))

(defn appraisal-page []
  (rf/dispatch [:revops/fetch-appraisals])
  (let [modal-open? (r/atom false)
        focus-year  (r/atom nil)]
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            user       @(rf/subscribe [:auth/current-user])
            route      @(rf/subscribe [:current-route-name])
            sorted     (->> appraisals (sort-by (juxt :year :month) #(compare %2 %1)))
            active     (first (filter #(not= (:status %) "LOCKED") sorted))
            year-opts  (available-year-options sorted)
            shown-year (or (safe-int @focus-year)
                           (safe-int (:year active))
                           (current-year))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "admin" "apurações"]
          :title "Apuração EV mensal"
          :subtitle "Competências mensais, prévia e fechamento dos EVs"
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:navigate :revops/appraisal-preview])}
            [layout/icon "trend" {:width 14 :height 14}] "Prévia mensal"]
           [:button.btn.btn-primary
            {:on-click #(reset! modal-open? true)}
            [layout/icon "plus" {:width 14 :height 14}] "Nova competência"]]}

         [active-card active #(reset! modal-open? true)]

         [monthly-rail sorted active shown-year year-opts #(reset! focus-year %)]

         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "24px 24px 16px"}}
           [:h3 "Histórico mensal"]
           [:div.card-sub
            (str (count sorted) " competência"
                 (when (not= 1 (count sorted)) "s")
                 " criada" (when (not= 1 (count sorted)) "s"))]]
          [:table.table
           [:thead
            [:tr
             [:th "Competência"]
             [:th "Status"]
             [:th.center "EVs"]
             [:th.right "Total"]
             [:th "Criada em"]
             [:th "Encerrada em"]
             [:th.right "Ações"]]]
           [:tbody
            (if (empty? sorted)
              [:tr [:td {:col-span 7 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma apuração encontrada"]]
              (for [a sorted]
                ^{:key (:id a)}
                [:tr
                 [:td.name.num (month-label (:month a) (:year a))]
                 [:td
                  [status->badge (:status a)]
                  (when (:has_contestation a)
                    [:span.badge.badge-review
                     {:style {:margin-left "6px"}}
                     "contestação"])]
                 [:td.center.num (str (or (:ev_count a) "·"))]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:total_amount a)) "·"))]
                 [:td.num.muted (or (:created_at_short a) "·")]
                 [:td.num.muted (or (:closed_at_short a) "·")]
                 [:td.right [step-actions a]]]))]]]

         [new-appraisal-modal {:open? @modal-open? :on-close #(reset! modal-open? false)}]]))))
