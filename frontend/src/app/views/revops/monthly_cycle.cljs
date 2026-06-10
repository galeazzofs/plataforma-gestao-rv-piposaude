(ns app.views.revops.monthly-cycle
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Unified MonthlyCycle page — a vertical step rail fed from
;; GET /api/v1/monthly-cycles/:id (global component aggregator).
;;
;; Sequence: Apuração EV → Apuração CN → (quarter-end months only)
;; Bônus CN, Bônus EV e Bônus Liderança. The rail guides, never blocks.

(def ^:private full-steps
  ["DRAFT" "CALCULATING" "VALIDATING" "LIDER_REVIEW" "REVOPS_REVIEW" "LOCKED"])

(def ^:private full-step-labels
  {"DRAFT"         "Draft"
   "CALCULATING"   "Calculating"
   "VALIDATING"    "Validating"
   "LIDER_REVIEW"  "Líder Review"
   "REVOPS_REVIEW" "RevOps Review"
   "LOCKED"        "Locked"})

(def ^:private bonus-steps ["PENDING" "CALCULATING" "LOCKED"])

(def ^:private bonus-step-labels
  {"PENDING" "Pendente" "CALCULATING" "Calculando" "LOCKED" "Final"})

(def ^:private base-sequence
  [["ev_apuracao" "Apuração EV"]
   ["cn_apuracao" "Apuração CN"]])

(def ^:private quarter-end-sequence
  [["cn_bonus" "Bônus CN"]
   ["ev_bonus" "Bônus EV"]
   ["leadership_bonus" "Bônus Liderança"]])

(defn components-for
  "Ordered [key label] sequence for a cycle. The quarterly bonuses only
   appear on the last month of each quarter."
  [cycle]
  (if (:is_quarter_end cycle)
    (into base-sequence quarter-end-sequence)
    base-sequence))

(def ^:private component-routes
  {"ev_apuracao"      :revops/appraisal
   "cn_apuracao"      :revops/cn-appraisal
   "cn_bonus"         :revops/cn-quarterly-bonus
   "ev_bonus"         :revops/ev-bonus
   "leadership_bonus" :revops/leadership})

(def ^:private month-names
  ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
   "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(defn cycle-label [{:keys [month year]}]
  (str (nth month-names (dec month) month) "/" year))

;; ── Pure rail helpers ───────────────────────────────────────────────

(defn component-of
  "Component map for key `k` — payload keys may arrive as keywords or
   strings depending on the JSON decoding path."
  [cycle k]
  (or (get-in cycle [:components (keyword k)])
      (get-in cycle [:components k])))

(defn current-step-key
  "First component in sequence order that is not LOCKED — the step the
   admin should be working on. nil when everything is locked."
  [cycle]
  (->> (components-for cycle)
       (map first)
       (remove #(= "LOCKED" (:status (component-of cycle %))))
       first))

(defn progress
  "{:done n :total m} counting LOCKED components."
  [cycle]
  (let [ks (map first (components-for cycle))]
    {:done  (count (filter #(= "LOCKED" (:status (component-of cycle %))) ks))
     :total (count ks)}))

(defn prev-month [{:keys [month year]}]
  (if (> month 1)
    {:month (dec month) :year year}
    {:month 12 :year (dec year)}))

(defn cycle-for-month [cycles {:keys [month year]}]
  (first (filter #(and (= (:month %) month) (= (:year %) year))
                 (or cycles []))))

(defn next-action
  "Primary inline action for component `k` in its current state.
   {:kind :request ...} actions run through :revops/cycle-action;
   {:kind :navigate :route ...} deep-link to the detail page (work that
   needs inputs). nil = nothing for the admin to click right now."
  [k component cycle]
  (let [{:keys [status appraisal_id rows expected]} component
        {:keys [month year quarter]} cycle]
    (case k
      "ev_apuracao"
      (case status
        "PENDING"
        {:kind :request :label "Criar apuração (DRAFT)"
         :method :post :url (ep/appraisals)
         :body {:month month :year year}
         :success-msg "Apuração criada em DRAFT."}
        "DRAFT"
        (when appraisal_id
          {:kind :request :label "Rodar cálculo"
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "CALCULATING"}
           :success-msg "Cálculo concluído. Revise antes de liberar."})
        "CALCULATING"
        (when appraisal_id
          {:kind :request :label "Liberar para validação"
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "VALIDATING"}
           :success-msg "Liberado para validação dos EVs."})
        "VALIDATING" nil
        "LIDER_REVIEW"
        (when appraisal_id
          {:kind :request :label "Avançar para revisão RevOps"
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "REVOPS_REVIEW"}
           :success-msg "Enviado para revisão RevOps."})
        "REVOPS_REVIEW"
        (when appraisal_id
          {:kind :request :label "Travar (LOCKED)" :confirm? true
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "LOCKED"}
           :success-msg "Apuração EV travada."})
        nil)

      "cn_apuracao"
      (case status
        "PENDING"
        {:kind :navigate :label "Preparar e rodar →"
         :route :revops/cn-appraisal}
        ("DRAFT" "CALCULATING")
        (if (and rows expected (< rows expected))
          ;; Incomplete row set (e.g. CN hired after the run): bulk
          ;; transitions would no-op — the remedy is re-running from the
          ;; detail page, which recreates non-LOCKED rows for all CNs.
          {:kind :navigate :label "Completar apuração →"
           :route :revops/cn-appraisal}
          {:kind :request :label "Liberar para validação"
           :method :post :url ep/cn-appraisal-transition-month
           :body {:month month :year year :to "VALIDATING"}
           :success-msg "CNs liberados para validação."})
        "VALIDATING"
        {:kind :request :label "Avançar para revisão do líder" :confirm? true
         :method :post :url ep/cn-appraisal-transition-month
         :body {:month month :year year :to "LIDER_REVIEW"}
         :success-msg "CNs avançados para revisão do líder."}
        "LIDER_REVIEW"
        {:kind :request :label "Avançar para revisão RevOps"
         :method :post :url ep/cn-appraisal-transition-month
         :body {:month month :year year :to "REVOPS_REVIEW"}
         :success-msg "CNs avançados para revisão RevOps."}
        "REVOPS_REVIEW"
        {:kind :request :label "Finalizar todos" :confirm? true
         :method :post :url ep/cn-appraisal-finalize-month
         :body {:month month :year year}
         :success-msg "Apurações CN finalizadas."}
        nil)

      "cn_bonus"
      (case status
        "PENDING"
        {:kind :request :label "Rodar Bônus CN"
         :method :post :url ep/cn-quarterly-bonus
         :body {:quarter quarter :year year}
         :success-msg "Bônus CN calculado."}
        "CALCULATING"
        {:kind :request :label "Finalizar Bônus CN" :confirm? true
         :method :post :url ep/cn-quarterly-bonus-finalize
         :body {:quarter quarter :year year}
         :success-msg "Bônus CN finalizado."}
        nil)

      "ev_bonus"
      (case status
        "PENDING"
        {:kind :request :label "Rodar Bônus EV"
         :method :post :url ep/ev-bonus
         :body {:quarter quarter :year year}
         :success-msg "Bônus EV calculado."}
        "CALCULATING"
        {:kind :request :label "Finalizar Bônus EV" :confirm? true
         :method :post :url ep/ev-bonus-finalize
         :body {:quarter quarter :year year}
         :success-msg "Bônus EV finalizado."}
        nil)

      "leadership_bonus"
      (case status
        "PENDING"
        {:kind :navigate :label "Preparar e rodar →"
         :route :revops/leadership}
        "CALCULATING"
        (when appraisal_id
          {:kind :request :label "Liberar para validação"
           :method :post :url (ep/leadership-transition appraisal_id)
           :body {:to "VALIDATING"}
           :success-msg "Liberado para validação do líder."})
        "VALIDATING" nil
        "LIDER_REVIEW"
        (when appraisal_id
          {:kind :request :label "Avançar para revisão RevOps"
           :method :post :url (ep/leadership-transition appraisal_id)
           :body {:to "REVOPS_REVIEW"}
           :success-msg "Enviado para revisão RevOps."})
        "REVOPS_REVIEW"
        (when appraisal_id
          {:kind :request :label "Travar (LOCKED)" :confirm? true
           :method :post :url (ep/leadership-transition appraisal_id)
           :body {:to "LOCKED"}
           :success-msg "Bônus Liderança travado."})
        nil)

      nil)))

(defn- next-month [{:keys [month year]}]
  (if (< month 12)
    {:month (inc month) :year year}
    {:month 1 :year (inc year)}))

(defn current-cycle-suggestion
  ([] (current-cycle-suggestion (js/Date.)))
  ([date]
   {:month (inc (.getMonth date))
    :year (.getFullYear date)}))

(defn suggest-cycle
  "Suggest the cycle that should be opened next.
   With no existing cycles, default to the current month. If the most recent
   cycle is LOCKED and there's no cycle yet for the following month, suggest
   that following month."
  ([cycles last-cycle]
   (suggest-cycle cycles last-cycle (js/Date.)))
  ([cycles last-cycle today]
   (cond
     (empty? (or cycles []))
     (current-cycle-suggestion today)

     (and last-cycle (= "LOCKED" (:status last-cycle)))
     (let [{:keys [month year] :as nm} (next-month last-cycle)
           already? (some #(and (= (:month %) month)
                                 (= (:year %) year))
                          cycles)]
       (when-not already? nm)))))

(defn- pick-cycle
  "Default to the most-recent OPEN cycle, falling back to the latest row."
  [cycles]
  (let [sorted (->> (or cycles [])
                    (sort-by (juxt :year :month) #(compare %2 %1)))]
    (or (first (filter #(= "OPEN" (:status %)) sorted))
        (first sorted))))

(defn- status->badge [status]
  (case status
    "PENDING"       [:span.badge.badge-locked "Pendente"]
    "DRAFT"         [:span.badge.badge-draft "Draft"]
    "CALCULATING"   [:span.badge.badge-calc "Calculating"]
    "VALIDATING"    [:span.badge.badge-validating "Validating"]
    "LIDER_REVIEW"  [:span.badge.badge-review "Líder Review"]
    "REVOPS_REVIEW" [:span.badge.badge-review "RevOps Review"]
    "LOCKED"        [:span.badge.badge-paid "Locked"]
    [:span.badge.badge-locked (or status "·")]))

(defn- mini-stepper
  "Per-component state mini-stepper. Bonus components use the short
   vocabulary; apurações/liderança use the full state machine."
  [k current-status]
  (let [bonus? (#{"cn_bonus" "ev_bonus"} k)
        sts    (if bonus? bonus-steps full-steps)
        labels (if bonus? bonus-step-labels full-step-labels)
        idx    (max 0 (.indexOf (clj->js sts) (or current-status (first sts))))]
    [:div.stepper
     (for [[i s] (map-indexed vector sts)
           :let [done?    (< i idx)
                 current? (= i idx)]]
       ^{:key s}
       [:<>
        [:div.stepper-stack
         [:div {:class (str "step" (cond done? " done" current? " current"))}
          [:div.step-dot (str (inc i))]]
         [:div.step-label (labels s)]]
        (when (< i (dec (count sts)))
          [:div.step-line])])]))

(defn- step-summary
  "One line with the numbers that matter for a component."
  [k component]
  (let [{:keys [validations_total validations_done rows final expected
                month has_contestation]} component
        text (cond
               (and validations_total (pos? validations_total))
               (str validations_done " / " validations_total
                    " validações concluídas")

               (= k "cn_apuracao")
               (if (and rows (pos? rows))
                 (str rows " de " (or expected rows) " CNs apurados"
                      (when month (str " · mês " month)))
                 "—")

               (and rows (pos? rows))
               (str (or final 0) " / " rows " finais"
                    (when expected (str " · " rows " de " expected)))

               :else "—")]
    [:<>
     [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
      text]
     (when has_contestation
       [:span.badge.badge-review {:style {:margin-top "6px"}}
        "⚠ contestação aberta"])]))

(defn- action-button [cycle {:keys [kind label confirm? route] :as action}]
  (when action
    [:button.btn.btn-primary.btn-sm
     {:on-click
      (fn []
        (cond
          (= kind :navigate)
          (rf/dispatch [:navigate route])

          (and confirm?
               (not (js/confirm (str label "? Esta ação avança o ciclo."))))
          nil

          :else
          (rf/dispatch [:revops/cycle-action
                        (assoc action :cycle-id (:id cycle))])))}
     label]))

(defn- detail-link [cycle k]
  (when-let [route (component-routes k)]
    (let [{:keys [month year quarter]} cycle
          query (if (#{"cn_bonus" "ev_bonus" "leadership_bonus"} k)
                  {:quarter quarter :year year}
                  {:month month :year year})]
      [:button.btn.btn-secondary.btn-sm
       {:on-click #(rf/dispatch [:navigate [route nil query]])}
       "Ver detalhes →"])))

(defn- bonus-guidance
  "Soft warning when a bonus step is opened while apurações are open.
   Guides, never blocks."
  [cycle k]
  (when (and (#{"cn_bonus" "ev_bonus" "leadership_bonus"} k)
             (some #(not= "LOCKED" (:status (component-of cycle %)))
                   ["ev_apuracao" "cn_apuracao"]))
    [:div.callout {:style {:margin "8px 0"}}
     [layout/icon "info" {:width 16 :height 16}]
     [:div {:style {:font-size "12px" :color "var(--fg-3)"}}
      "Recomendado concluir as Apurações EV e CN antes dos bônus."]]))

(defn- step-card
  [cycle idx k label {:keys [expanded? current? read-only? on-toggle]}]
  (let [component (component-of cycle k)
        status    (or (:status component) "PENDING")
        done?     (= "LOCKED" status)]
    [:div.card {:style {:margin-top "12px"
                        :border (when current?
                                  "1px solid var(--accent, #4f7cff)")
                        :opacity (if (or done? current? expanded?) 1 0.72)}}
     [:div.card-head {:style {:cursor "pointer"} :on-click on-toggle}
      [:div {:style {:display "flex" :align-items "center" :gap "10px"}}
       [:div.step-dot {:style {:flex-shrink 0}} (if done? "✓" (str idx))]
       [:div
        [:h4 label]
        (when current?
          [:div.card-sub "Você está aqui"])]]
      [:div {:style {:display "flex" :gap "10px" :align-items "center"}}
       (when-not expanded? [step-summary k component])
       [status->badge status]]]
     (when expanded?
       [:div {:style {:padding "4px 0 8px"}}
        (when-not (= "PENDING" status)
          [mini-stepper k status])
        [:div {:style {:padding "10px 0"}}
         [step-summary k component]]
        [bonus-guidance cycle k]
        (when (= "VALIDATING" status)
          [:div.muted {:style {:font-size "12px" :margin-bottom "8px"}}
           (if (= k "ev_apuracao")
             "Aguardando os EVs validarem; avança sozinho ao concluir."
             "Aguardando validações.")])
        [:div {:style {:display "flex" :gap "8px" :margin-top "4px"}}
         (when-not read-only?
           [action-button cycle (next-action k component cycle)])
         [detail-link cycle k]]])]))

(defn- quarter-divider [cycle]
  [:div {:style {:display "flex" :align-items "center" :gap "12px"
                 :margin "20px 0 4px"}}
   [:div {:style {:flex 1 :height "1px" :background "var(--border, #333)"}}]
   [:strong {:style {:font-size "12px" :letter-spacing "0.08em"
                     :color "var(--fg-3)"}}
    (str "FECHAMENTO DO Q" (:quarter cycle))]
   [:div {:style {:flex 1 :height "1px" :background "var(--border, #333)"}}]])

(defn- next-action-band [cycle]
  (when (not= "LOCKED" (:status cycle))
    (let [k         (current-step-key cycle)
          labels    (into {} (components-for cycle))
          component (component-of cycle k)
          action    (when k (next-action k component cycle))]
      (when k
        [:div.callout {:style {:margin-top "16px"}}
         [layout/icon "info" {:width 20 :height 20}]
         [:div {:style {:flex 1}}
          [:strong (str "Próximo passo: " (get labels k))]
          [:div {:style {:font-size "13px" :color "var(--fg-3)"}}
           (if action
             (:label action)
             "Aguardando validações — nada a fazer agora.")]]
         (when action [action-button cycle action])]))))

(defn- progress-bar [cycle]
  (let [{:keys [done total]} (progress cycle)]
    [:div {:style {:display "flex" :align-items "center" :gap "10px"}}
     [:div {:style {:flex 1 :height "6px" :border-radius "3px"
                    :background "var(--bg-3, #222)" :overflow "hidden"}}
      [:div {:style {:width (str (if (pos? total)
                                   (js/Math.round (* 100 (/ done total)))
                                   0) "%")
                     :height "100%"
                     :background "var(--accent, #4f7cff)"}}]]
     [:span.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
      (str done " de " total " passos concluídos")]]))

(defn- cycle-selector [cycles selection]
  (let [cyc    (cycle-for-month cycles selection)
        sorted (->> (or cycles [])
                    (sort-by (juxt :year :month) #(compare %2 %1)))]
    [:div.card {:style {:display "flex" :align-items "center" :gap "12px"
                        :padding "14px 18px"}}
     [:button.btn.btn-secondary.btn-sm
      {:on-click #(rf/dispatch [:revops/select-cycle-month
                                (prev-month selection)])}
      "‹"]
     [:div {:style {:flex 1 :text-align "center"}}
      [:strong {:style {:font-size "16px"}} (cycle-label selection)]
      [:span {:style {:margin-left "10px"}}
       (cond
         (nil? cyc)                    [:span.badge.badge-locked "Sem ciclo"]
         (= "OPEN" (:status cyc))      [:span.badge.badge-calc "Em andamento"]
         (= "LOCKED" (:status cyc))    [:span.badge.badge-paid "Fechado"]
         :else                         [:span.badge.badge-locked (:status cyc)])]]
     [:button.btn.btn-secondary.btn-sm
      {:on-click #(rf/dispatch [:revops/select-cycle-month
                                (next-month selection)])}
      "›"]
     (when (seq sorted)
       [:select {:value     (str (:month selection) "-" (:year selection))
                 :on-change (fn [e]
                              (let [[m y] (.split (.. e -target -value) "-")]
                                (rf/dispatch [:revops/select-cycle-month
                                              {:month (js/parseInt m)
                                               :year  (js/parseInt y)}])))
                 :style {:margin-left "8px"}}
        (when (nil? (cycle-for-month sorted selection))
          [:option {:value (str (:month selection) "-" (:year selection))}
           (cycle-label selection)])
        (for [c sorted]
          ^{:key (:id c)}
          [:option {:value (str (:month c) "-" (:year c))}
           (str (cycle-label c)
                (if (= "LOCKED" (:status c)) " · fechado" " · aberto"))])])]))

(defn- delete-cycle-btn [cycle]
  (let [{:keys [id status]} cycle
        locked? (= "LOCKED" status)]
    [:button.btn.btn-danger.btn-sm
     {:disabled locked?
      :title    (if locked?
                  "Ciclos LOCKED não podem ser excluídos."
                  "Excluir este ciclo mensal.")
      :on-click #(when (js/confirm
                        (str "Tem certeza que deseja excluir o ciclo "
                             (cycle-label cycle) "? "
                             "Esta ação não pode ser desfeita."))
                   (rf/dispatch [:revops/delete-monthly-cycle id]))}
     "Excluir ciclo"]))

(defn- open-cycle-cta [selection]
  [:div.card
   [:div.empty
    [:h4 (str "Nenhum ciclo para " (cycle-label selection))]
    [:p "Abra o ciclo para começar a apuração deste mês."]
    [:button.btn.btn-primary
     {:on-click #(rf/dispatch [:revops/open-monthly-cycle selection])}
     (str "Abrir " (cycle-label selection))]]])

(defn- rail [cycle read-only? expanded toggle!]
  (let [comps (components-for cycle)
        cur   (when-not read-only? (current-step-key cycle))]
    [:<>
     (for [[i [k label]] (map-indexed vector comps)]
       ^{:key k}
       [:<>
        (when (= k "cn_bonus") [quarter-divider cycle])
        [step-card cycle (inc i) k label
         {:expanded?  (or (contains? @expanded k)
                          (and (not read-only?) (= k cur)))
          :current?   (= k cur)
          :read-only? read-only?
          :on-toggle  #(toggle! k)}]])]))

(defn page []
  (rf/dispatch [:revops/fetch-monthly-cycles])
  (let [expanded (r/atom #{})
        toggle!  (fn [k] (swap! expanded
                                #(if (contains? % k) (disj % k) (conj % k))))]
    (fn []
      (let [cycles    @(rf/subscribe [:revops/monthly-cycles])
            loading?  @(rf/subscribe [:revops/monthly-cycle-loading?])
            user      @(rf/subscribe [:auth/current-user])
            route     @(rf/subscribe [:current-route-name])
            selection (or @(rf/subscribe [:revops/monthly-cycle-selection])
                          (when-let [t (pick-cycle cycles)]
                            {:month (:month t) :year (:year t)})
                          (current-cycle-suggestion))
            target    (cycle-for-month cycles selection)
            detail         @(rf/subscribe [:revops/monthly-cycle])
            requested-id   @(rf/subscribe [:revops/monthly-cycle-requested-id])
            error?         @(rf/subscribe [:revops/monthly-cycle-error?])
            cycle          (when (and detail target (= (:id detail) (:id target)))
                             detail)
            read-only? (= "LOCKED" (:status cycle))]
        (when (and target
                   (not= (:id target) requested-id)
                   (or (not detail) (not= (:id detail) (:id target))))
          (rf/dispatch [:revops/fetch-monthly-cycle-detail (:id target)]))
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "admin" "ciclo mensal"]
          :title "Ciclo Mensal"
          :subtitle "Sequência da apuração: EVs, CNs e — no fechamento do trimestre — os bônus"
          :header-actions (when cycle (delete-cycle-btn cycle))}

         [cycle-selector cycles selection]

         (cond
           (not target)
           [open-cycle-cta selection]

           (and error? (not cycle))
           [:div.card
            [:div {:style {:padding "32px" :text-align "center"
                           :color "var(--fg-3)"}}
             [:div {:style {:margin-bottom "12px"}}
              "Erro ao carregar o ciclo."]
             [:button.btn.btn-secondary.btn-sm
              {:on-click #(rf/dispatch [:revops/fetch-monthly-cycle-detail
                                        (:id target)])}
              "Tentar novamente"]]]

           (or loading? (not cycle))
           [:div.card [:div {:style {:padding "32px" :text-align "center"
                                      :color "var(--fg-3)"}} "Carregando…"]]

           :else
           [:<>
            [:div.card {:style {:padding "16px 20px" :margin-top "16px"}}
             [progress-bar cycle]]
            (if read-only?
              (let [nm (next-month {:month (:month cycle)
                                    :year  (:year cycle)})]
                [:div.callout {:style {:margin-top "16px"}}
                 [layout/icon "info" {:width 20 :height 20}]
                 [:div {:style {:flex 1}}
                  [:strong "Ciclo fechado"]
                  [:div {:style {:font-size "13px" :color "var(--fg-3)"}}
                   (str "Travado em "
                        (some-> (:locked_at cycle) (subs 0 10))
                        ". Histórico em modo leitura.")]]
                 (when-not (cycle-for-month cycles nm)
                   [:button.btn.btn-primary.btn-sm
                    {:on-click #(do (rf/dispatch [:revops/select-cycle-month nm])
                                    (rf/dispatch [:revops/open-monthly-cycle nm]))}
                    (str "Abrir " (cycle-label nm))])])
              [next-action-band cycle])
            [rail cycle read-only? expanded toggle!]])]))))
