(ns app.views.revops.cn-goals
  "Metas Mensais · CN — RevOps define a meta SAO de cada CN ativo.

   Estado em app-db ([:admin :cn-goals-page]). Edições ficam num mapa
   indexado por período ([year month]), então trocar de mês nunca descarta
   trabalho não salvo; salvar só limpa o período salvo, e falha de save
   preserva tudo."
  (:require [re-frame.core :as rf]
            [clojure.string :as str]
            [app.api.endpoints :as ep]
            [app.views.cn.calc :as calc]
            [app.ds.layout :as layout]
            [app.ds.empty-state :refer [empty-state]]
            [app.auth.subs]))

;; ── Pure helpers ───────────────────────────────────────────────────────────

(def month-short ["jan" "fev" "mar" "abr" "mai" "jun"
                  "jul" "ago" "set" "out" "nov" "dez"])
(def month-full ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
                 "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(defn period-key [{:keys [month year]}] [year month])
(defn parse-period-key [[year month]] {:month month :year year})

(defn period-label-short [{:keys [month year]}]
  (str (nth month-short (dec month) month) "/" year))

(defn period-title [{:keys [month year]}]
  (str (nth month-full (dec month) month) " " year))

(defn current-period [^js date]
  {:month (inc (.getMonth date)) :year (.getFullYear date)})

(defn prev-period [{:keys [month year]}]
  (if (= month 1)
    {:month 12 :year (dec year)}
    {:month (dec month) :year year}))

(defn year-options
  "2025 até o ano seguinte ao atual — metas são definidas com antecedência."
  [current-year]
  (vec (range 2025 (+ current-year 2))))

(defn parse-sao
  "Parse estrito de meta SAO: dígitos com no máximo um separador decimal
   (vírgula ou ponto). Sem sinal, sem separador de milhar. nil quando não
   reconhece — dinheiro malformado nunca vira número por acaso."
  [v]
  (cond
    (number? v) v
    (and (string? v)
         (re-matches #"\d+([.,]\d*)?" (str/trim v)))
    (calc/->num v)
    :else nil))

(defn sao-valid? [v]
  (let [s (str (or v ""))]
    (or (str/blank? s) (some? (parse-sao s)))))

(defn fmt-sao
  "Exibição pt-BR da meta SAO — contagem, não dinheiro (\"6.00\" → \"6\",
   \"6.5\" → \"6,5\"). nil quando não numérico."
  [v]
  (when-let [n (parse-sao v)]
    (.toLocaleString n "pt-BR" #js {:maximumFractionDigits 2})))

(defn num->input
  "Número → string editável (vírgula decimal, sem milhar)."
  [n]
  (str/replace (str n) "." ","))

(defn fmt-int [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (.toLocaleString (js/Math.round n) "pt-BR")))))

(defn edited? [edits cn-id] (contains? edits cn-id))

(defn input-display
  "Valor exibido no input: edição crua se houver, senão o salvo formatado."
  [row edits]
  (if (edited? edits (:cn_id row))
    (or (get-in edits [(:cn_id row) :sao_target]) "")
    (or (fmt-sao (:sao_target row)) "")))

(defn effective-sao-num [row edits]
  (let [raw (if (edited? edits (:cn_id row))
              (get-in edits [(:cn_id row) :sao_target])
              (:sao_target row))]
    (or (parse-sao raw) 0)))

(defn row-vidas [row edits]
  (calc/vidas-meta-from-sao (effective-sao-num row edits) (:porte row)))

(defn totals [rows edits]
  (reduce (fn [acc row]
            (-> acc
                (update :sao + (effective-sao-num row edits))
                (update :vidas + (or (row-vidas row edits) 0))))
          {:sao 0 :vidas 0}
          rows))

(defn build-items
  "Edições do período → payload do PUT. Decimal sempre com ponto."
  [period-edits]
  (mapv (fn [[cn-id m]]
          {:cn_id cn-id
           :sao_target (str (or (parse-sao (:sao_target m)) 0))})
        period-edits))

(defn merge-prev-edits
  "Semeia edições a partir do mês anterior: só linhas cujo SAO efetivo é
   zero e cujo mês anterior tem meta positiva. Nada é salvo aqui."
  [rows prev-rows period-edits]
  (let [prev-by-id (into {} (map (juxt :cn_id identity)) prev-rows)]
    (reduce
     (fn [{:keys [edits] :as acc} row]
       (let [cn-id  (:cn_id row)
             cur    (effective-sao-num row edits)
             prev-n (some-> (get prev-by-id cn-id) :sao_target parse-sao)]
         (if (and (zero? cur) prev-n (pos? prev-n))
           (-> acc
               (assoc-in [:edits cn-id :sao_target] (num->input prev-n))
               (update :applied inc))
           acc)))
     {:edits (or period-edits {}) :applied 0}
     rows)))

(defn coverage-state
  "Estado do mês para o dot do chip: :full quando todo CN ativo tem meta,
   :part quando alguns, nil quando nenhum (ou sem dados)."
  [covered total]
  (when (and covered total (pos? total) (pos? covered))
    (if (>= covered total) :full :part)))

;; ── Events ─────────────────────────────────────────────────────────────────

(def ^:private page-path [:admin :cn-goals-page])

(rf/reg-event-fx
 :cn-goals/init
 (fn [{:keys [db]} [_ default-period]]
   (let [period (or (get-in db (conj page-path :period)) default-period)]
     {:db (assoc-in db (conj page-path :period) period)
      :fx [[:dispatch [:cn-goals/fetch period]]
           [:dispatch [:cn-goals/fetch-coverage (:year period)]]]})))

(rf/reg-event-fx
 :cn-goals/select-period
 (fn [{:keys [db]} [_ period]]
   (let [old-year (get-in db (conj page-path :period :year))]
     {:db (assoc-in db (conj page-path :period) period)
      :fx (cond-> [[:dispatch [:cn-goals/fetch period]]]
            (not= (:year period) old-year)
            (conj [:dispatch [:cn-goals/fetch-coverage (:year period)]]))})))

(rf/reg-event-fx
 :cn-goals/fetch
 (fn [{:keys [db]} [_ {:keys [month year]}]]
   {:db (-> db
            (assoc-in (conj page-path :loading?) true)
            (assoc-in (conj page-path :error) nil))
    :http {:method     :get
           :url        (str ep/cn-goals "?month=" month "&year=" year)
           :on-success [:cn-goals/loaded]
           :on-failure [:cn-goals/load-failed]}}))

(rf/reg-event-db
 :cn-goals/loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in (conj page-path :rows) (:data response))
       (assoc-in (conj page-path :loading?) false))))

(rf/reg-event-db
 :cn-goals/load-failed
 (fn [db _]
   (-> db
       (assoc-in (conj page-path :loading?) false)
       (assoc-in (conj page-path :error)
                 "Não foi possível carregar as metas deste período."))))

(rf/reg-event-fx
 :cn-goals/fetch-coverage
 (fn [_ [_ year]]
   {:http {:method     :get
           :url        (str ep/cn-goals-coverage "?year=" year)
           :on-success [:cn-goals/coverage-loaded year]
           :on-failure [:cn-goals/coverage-failed]}}))

(rf/reg-event-db
 :cn-goals/coverage-loaded
 (fn [db [_ year response]]
   (let [months (into {}
                      (map (fn [[k v]] [(js/parseInt (name k) 10) v]))
                      (get-in response [:data :months]))]
     (assoc-in db (conj page-path :coverage)
               {:year       year
                :active-cns (get-in response [:data :active_cns])
                :months     months}))))

(rf/reg-event-db
 :cn-goals/coverage-failed
 (fn [db _] (assoc-in db (conj page-path :coverage) nil)))

(rf/reg-event-db
 :cn-goals/edit
 (fn [db [_ cn-id value]]
   (let [pkey (period-key (get-in db (conj page-path :period)))]
     (assoc-in db (conj page-path :edits pkey cn-id :sao_target) value))))

(rf/reg-event-db
 :cn-goals/revert
 (fn [db [_ cn-id]]
   (let [pkey (period-key (get-in db (conj page-path :period)))
         db'  (update-in db (conj page-path :edits pkey) dissoc cn-id)]
     (if (empty? (get-in db' (conj page-path :edits pkey)))
       (update-in db' (conj page-path :edits) dissoc pkey)
       db'))))

(rf/reg-event-db
 :cn-goals/discard-current
 (fn [db _]
   (let [pkey (period-key (get-in db (conj page-path :period)))]
     (update-in db (conj page-path :edits) dissoc pkey))))

(rf/reg-event-fx
 :cn-goals/save
 (fn [{:keys [db]} _]
   (let [period (get-in db (conj page-path :period))
         pkey   (period-key period)
         items  (build-items (get-in db (conj page-path :edits pkey)))]
     (if (seq items)
       {:db (assoc-in db (conj page-path :saving?) true)
        :http {:method     :put
               :url        ep/cn-goals
               :body       {:month (:month period) :year (:year period)
                            :items items}
               :on-success [:cn-goals/saved period pkey (count items)]
               :on-failure [:cn-goals/save-failed]}}
       {}))))

(rf/reg-event-fx
 :cn-goals/saved
 (fn [{:keys [db]} [_ period pkey n _response]]
   {:db (-> db
            (assoc-in (conj page-path :saving?) false)
            (update-in (conj page-path :edits) dissoc pkey))
    :fx [[:dispatch [:cn-goals/fetch period]]
         [:dispatch [:cn-goals/fetch-coverage (:year period)]]
         [:dispatch [:ui/show-toast
                     {:type :success
                      :message (str "Metas de " (period-label-short period)
                                    " salvas (" n " CN" (when (> n 1) "s") ")")}]]]}))

(rf/reg-event-fx
 :cn-goals/save-failed
 (fn [{:keys [db]} [_ response]]
   {:db (assoc-in db (conj page-path :saving?) false)
    :dispatch [:ui/show-toast
               {:type :error
                :message (or (get-in response [:response :error :message])
                             "Erro ao salvar. Suas edições foram mantidas.")}]}))

(rf/reg-event-fx
 :cn-goals/copy-from-prev
 (fn [{:keys [db]} _]
   (let [period (get-in db (conj page-path :period))
         prev   (prev-period period)]
     {:http {:method     :get
             :url        (str ep/cn-goals "?month=" (:month prev)
                              "&year=" (:year prev))
             :on-success [:cn-goals/copy-loaded prev period]
             :on-failure [:cn-goals/copy-failed prev]}})))

(rf/reg-event-fx
 :cn-goals/copy-loaded
 (fn [{:keys [db]} [_ prev target-period response]]
   (let [period (get-in db (conj page-path :period))]
     ;; O usuário pode ter trocado de mês durante a chamada; só aplica se
     ;; ainda está olhando para o período que pediu a cópia.
     (if-not (= period target-period)
       {}
       (let [pkey (period-key period)
             {:keys [edits applied]}
             (merge-prev-edits (get-in db (conj page-path :rows))
                               (:data response)
                               (get-in db (conj page-path :edits pkey)))]
         (if (pos? applied)
           {:db (assoc-in db (conj page-path :edits pkey) edits)
            :dispatch [:ui/show-toast
                       {:type :info
                        :message (str applied " meta" (when (> applied 1) "s")
                                      " copiada" (when (> applied 1) "s")
                                      " de " (period-label-short prev)
                                      ". Revise e salve.")}]}
           {:dispatch [:ui/show-toast
                       {:type :warning
                        :message (str "Nada para copiar de "
                                      (period-label-short prev) ".")}]}))))))

(rf/reg-event-fx
 :cn-goals/copy-failed
 (fn [_ [_ prev]]
   {:dispatch [:ui/show-toast
               {:type :error
                :message (str "Erro ao buscar as metas de "
                              (period-label-short prev) ".")}]}))

;; ── Subs ───────────────────────────────────────────────────────────────────

(rf/reg-sub :cn-goals/period (fn [db _] (get-in db (conj page-path :period))))
(rf/reg-sub :cn-goals/rows (fn [db _] (get-in db (conj page-path :rows) [])))
(rf/reg-sub :cn-goals/loading? (fn [db _] (get-in db (conj page-path :loading?))))
(rf/reg-sub :cn-goals/saving? (fn [db _] (get-in db (conj page-path :saving?))))
(rf/reg-sub :cn-goals/error (fn [db _] (get-in db (conj page-path :error))))
(rf/reg-sub :cn-goals/coverage (fn [db _] (get-in db (conj page-path :coverage))))

(rf/reg-sub
 :cn-goals/edits
 (fn [db _]
   (let [{:keys [period edits]} (get-in db page-path)]
     (get edits (period-key period) {}))))

(rf/reg-sub
 :cn-goals/dirty-periods
 (fn [db _]
   (let [{:keys [period edits]} (get-in db page-path)
         cur (period-key period)]
     (->> edits
          (filter (fn [[k v]] (and (not= k cur) (seq v))))
          (map key)
          sort))))

;; ── View ───────────────────────────────────────────────────────────────────

(defn- period-filter [{:keys [month year]} coverage]
  (let [cov-year? (= year (:year coverage))
        total     (:active-cns coverage)]
    [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
     (for [m (range 1 13)]
       (let [covered (when cov-year? (get-in coverage [:months m]))
             state   (coverage-state covered total)]
         ^{:key m}
         [:button {:type "button"
                   :class (str "chip" (when (= m month) " active"))
                   :aria-pressed (str (= m month))
                   :aria-label (str (nth month-full (dec m))
                                    (when state
                                      (str " · " covered " de " total
                                           " CNs com meta")))
                   :on-click #(rf/dispatch [:cn-goals/select-period
                                            {:month m :year year}])}
          (when state [:span.chip-cov {:class (name state) :aria-hidden "true"}])
          (nth month-short (dec m))]))
     [:div {:role "separator" :aria-hidden "true"
            :style {:width "1px" :height "20px"
                    :background "var(--border-subtle)" :margin "0 4px"}}]
     (for [y (year-options (:year (current-period (js/Date.))))]
       ^{:key y}
       [:button {:type "button"
                 :class (str "chip" (when (= y year) " active"))
                 :aria-pressed (str (= y year))
                 :on-click #(rf/dispatch [:cn-goals/select-period
                                          {:month month :year y}])}
        y])]))

(defn- porte-cell [{:keys [porte]}]
  (if-let [factor (get calc/porte-factors porte)]
    [:span {:style {:font-family "var(--font-mono)" :font-size "12px"
                    :color "var(--fg-2)"}}
     (str porte " ×" (fmt-int factor))]
    [:span.muted {:title "Configure o porte do CN em Configuração: Usuários"}
     "sem porte"]))

(defn- goal-row [idx row edits row-count]
  (let [cn-id    (:cn_id row)
        dirty?   (edited? edits cn-id)
        raw      (input-display row edits)
        invalid? (and dirty? (not (sao-valid? raw)))
        vidas    (row-vidas row edits)
        cn-name  (or (:cn_name row) (str "CN " cn-id))]
    [:tr
     [:td.name cn-name]
     [:td [porte-cell row]]
     [:td.right
      [:div.goal-cell
       [:div.goal-edit-row
        (when dirty?
          [:button.goal-revert
           {:type "button"
            :aria-label (str "Restaurar meta salva de " cn-name)
            :on-click #(rf/dispatch [:cn-goals/revert cn-id])}
           [layout/icon "refresh" {:width 12 :height 12}]])
        [:div.goal-input {:class (when invalid? "is-invalid")}
         [:input {:type "text"
                  :inputMode "decimal"
                  :id (str "cn-goal-input-" idx)
                  :placeholder "0"
                  :value raw
                  :aria-label (str "Meta SAO de " cn-name)
                  :aria-invalid (str (boolean invalid?))
                  :on-focus #(.select (.-target %))
                  :on-key-down (fn [e]
                                 (when (and (= "Enter" (.-key e))
                                            (< (inc idx) row-count))
                                   (.preventDefault e)
                                   (some-> (.getElementById
                                            js/document
                                            (str "cn-goal-input-" (inc idx)))
                                           (.focus))))
                  :on-change #(rf/dispatch [:cn-goals/edit cn-id
                                            (.. % -target -value)])}]]]
       (cond
         invalid? [:span.goal-error "valor inválido"]
         (and dirty? (some? (:sao_target row)))
         [:span.goal-was (str "era " (fmt-sao (:sao_target row)))])]]
     [:td.right.num
      (cond
        (nil? (:porte row))      [:span.muted "defina o porte"]
        (and vidas (pos? vidas)) (fmt-int vidas)
        :else                    "·")]]))

(defn- skeleton-rows []
  (for [i (range 4)]
    ^{:key i}
    [:tr [:td.loading-cell {:col-span 4}
          [:div.skel-row
           [:div.skel {:style {:flex 2}}]
           [:div.skel {:style {:flex 1}}]
           [:div.skel {:style {:flex 1}}]
           [:div.skel {:style {:flex 1}}]]]]))

(defn- goals-table [{:keys [rows edits loading? period]}]
  (let [{:keys [sao vidas]} (totals rows edits)]
    [:div.goals-table-scroll
     [:table.table {:aria-label (str "Metas de " (period-title period))}
      [:thead
       [:tr
        [:th "CN"]
        [:th "Porte · Fator"]
        [:th.right "Meta SAO"]
        [:th.right "Meta Vidas (auto)"]]]
      [:tbody
       (cond
         (and loading? (empty? rows)) (skeleton-rows)
         :else (doall
                (map-indexed
                 (fn [idx row]
                   ^{:key (:cn_id row)}
                   [goal-row idx row edits (count rows)])
                 rows)))]
      (when (seq rows)
        [:tfoot
         [:tr.totals-row
          [:td {:col-span 2}
           [:span.totals-label
            (str "total · " (count rows) " CN" (when (> (count rows) 1) "s"))]]
          [:td.right.strong-num (or (fmt-sao sao) "0")]
          [:td.right.strong-num (or (fmt-int vidas) "0")]]])]]))

(defn- toolbar [{:keys [period coverage dirty-periods]}]
  (let [prev      (prev-period period)
        cov-year? (= (:year period) (:year coverage))
        covered   (when cov-year? (get-in coverage [:months (:month period)]))
        total     (:active-cns coverage)]
    [:div.table-toolbar
     [:div.toolbar-title
      [:h3 (period-title period)]
      (when (and cov-year? total (pos? total))
        [:div.card-sub
         (str covered " de " total " CNs com meta definida")])]
     [:div.toolbar-actions
      (when (seq dirty-periods)
        (into [:span.dirty-hint "não salvo: "]
              (interpose
               " · "
               (for [pk dirty-periods]
                 (let [p (parse-period-key pk)]
                   [:button {:type "button"
                             :on-click #(rf/dispatch
                                         [:cn-goals/select-period p])}
                    (period-label-short p)])))))
      [:button.btn.btn-ghost.btn-sm
       {:type "button"
        :title (str "Preenche CNs sem meta com os valores de "
                    (period-label-short prev) ". Nada é salvo até você salvar.")
        :on-click #(rf/dispatch [:cn-goals/copy-from-prev])}
       [layout/icon "doc" {:width 13 :height 13}]
       (str "Copiar de " (period-label-short prev))]]]))

(defn- load-error [error period]
  [:div.callout.-danger
   [layout/icon "alert" {:width 20 :height 20}]
   [:div.appraisal-callout-body
    [:strong "Erro ao carregar"]
    [:div.appraisal-callout-text error]]
   [:button.btn.btn-secondary.btn-sm
    {:type "button"
     :on-click #(rf/dispatch [:cn-goals/fetch period])}
    "Tentar novamente"]])

(defn page []
  (rf/dispatch [:cn-goals/init (current-period (js/Date.))])
  (fn []
    (let [period   @(rf/subscribe [:cn-goals/period])
          rows     @(rf/subscribe [:cn-goals/rows])
          loading? @(rf/subscribe [:cn-goals/loading?])
          saving?  @(rf/subscribe [:cn-goals/saving?])
          error    @(rf/subscribe [:cn-goals/error])
          edits    @(rf/subscribe [:cn-goals/edits])
          coverage @(rf/subscribe [:cn-goals/coverage])
          dirty    @(rf/subscribe [:cn-goals/dirty-periods])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          n-edits  (count edits)
          invalid? (some (fn [[_ m]] (not (sao-valid? (:sao_target m)))) edits)]
      (when period
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "metas cn"]
          :title "Metas Mensais · CN"
          :subtitle "Defina a meta SAO. A meta de vidas deriva do porte de cada CN."
          :header-actions
          [(when (pos? n-edits)
             [:button.btn.btn-ghost
              {:type "button"
               :title (str "Descarta as " n-edits " edições não salvas de "
                           (period-label-short period))
               :on-click #(rf/dispatch [:cn-goals/discard-current])}
              "Descartar"])
           [:button.btn.btn-primary
            {:type "button"
             :disabled (or saving? (zero? n-edits) (boolean invalid?))
             :title (when invalid? "Corrija os valores inválidos antes de salvar")
             :on-click #(rf/dispatch [:cn-goals/save])}
            [layout/icon "check" {:width 14 :height 14}]
            (cond
              saving?         "Salvando…"
              (pos? n-edits)  (str "Salvar metas · " n-edits)
              :else           "Salvar metas")]]}

         [period-filter period coverage]

         [:div.card {:style {:padding 0 :gap 0}}
          [toolbar {:period period :coverage coverage :dirty-periods dirty}]
          (cond
            (and error (empty? rows))
            [:div {:style {:padding "20px"}} [load-error error period]]

            (and (empty? rows) (not loading?))
            [empty-state
             {:icon "target"
              :title "Nenhum CN ativo"
              :description "Cadastre usuários com papel CN para definir metas mensais de SAO e vidas."
              :action-label "Gerenciar usuários"
              :on-action #(rf/dispatch [:navigate :revops/users])}]

            :else
            [goals-table {:rows rows :edits edits
                          :loading? loading? :period period}])]]))))
