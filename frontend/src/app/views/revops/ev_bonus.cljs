(ns app.views.revops.ev-bonus
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn ->num [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) n))))

(defn- count-num [v]
  (or (some-> v ->num js/Math.round) 0))

(defn available-years
  ([] (available-years (js/Date.)))
  ([date]
   (range 2024 (+ (.getFullYear date) 2))))

(defn run-summary-message [result]
  (let [computed  (count-num (:bonuses_computed result))
        final     (count-num (:skipped_final result))
        no-salary (count-num (:skipped_no_salary result))
        details   (keep identity
                        [(when (pos? final)
                           (str final " finais preservados"))
                         (when (pos? no-salary)
                           (str no-salary " sem salário base"))])]
    (str/join " · " (cons (str computed " bônus EV recalculados") details))))

(defn run-log-lines [result]
  (let [computed  (count-num (:bonuses_computed result))
        final     (count-num (:skipped_final result))
        no-salary (count-num (:skipped_no_salary result))]
    (cond-> [(if (pos? computed)
               (str computed " registros recalculados.")
               "Nenhum bônus foi recalculado.")]
      (pos? final)
      (conj (str final " registros já estavam finais e foram preservados."))

      (pos? no-salary)
      (conj (str no-salary " registros não rodaram por falta de salário base no cadastro do EV."))

      (and (zero? computed) (zero? final) (zero? no-salary))
      (conj "Não há atingimentos cadastrados para este trimestre. Gere ou edite Atingimento por EV antes de calcular o bônus."))))

(rf/reg-event-fx
 :revops/fetch-ev-bonus
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (-> db
              (assoc-in [:admin :ev-bonus-loading?] true)
              (assoc-in [:admin :ev-bonus-last-error] nil))
    :http {:method     :get
           :url        (str ep/ev-bonus "?quarter=" quarter "&year=" year)
           :on-success [:revops/ev-bonus-loaded]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-event-db
 :revops/ev-bonus-loaded
 (fn [db [_ r]] (-> db (assoc-in [:admin :ev-bonus] (:data r))
                       (assoc-in [:admin :ev-bonus-loading?] false))))

(rf/reg-event-fx
 :revops/ev-bonus-error
 (fn [{:keys [db]} [_ resp]]
   (let [msg (or (get-in resp [:error :message])
                 "Erro ao atualizar bônus EV")]
     {:db       (-> db
                    (assoc-in [:admin :ev-bonus-loading?] false)
                    (assoc-in [:admin :ev-bonus-last-error] msg))
      :dispatch [:ui/show-toast {:type :error :message msg}]})))

(rf/reg-event-fx
 :revops/run-ev-bonus
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (-> db
              (assoc-in [:admin :ev-bonus-loading?] true)
              (assoc-in [:admin :ev-bonus-run-log] nil)
              (assoc-in [:admin :ev-bonus-last-error] nil))
    :http {:method     :post
           :url        ep/ev-bonus
           :body       {:quarter quarter :year year}
           :on-success [:revops/ev-bonus-run-success quarter year]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-event-fx
 :revops/ev-bonus-run-success
 (fn [{:keys [db]} [_ quarter year resp]]
   (let [summary (run-summary-message (:data resp))]
     {:db         (-> db
                      (assoc-in [:admin :ev-bonus-run-log]
                                {:quarter quarter
                                 :year year
                                 :result (:data resp)})
                      (assoc-in [:admin :ev-bonus-loading?] false))
      :dispatch-n [[:revops/fetch-ev-bonus quarter year]
                   [:ui/show-toast {:type :success
                                    :message summary}]]})))

(rf/reg-sub :revops/ev-bonus (fn [db _] (get-in db [:admin :ev-bonus] [])))
(rf/reg-sub :revops/ev-bonus-loading? (fn [db _] (get-in db [:admin :ev-bonus-loading?])))
(rf/reg-sub :revops/ev-bonus-run-log (fn [db _] (get-in db [:admin :ev-bonus-run-log])))
(rf/reg-sub :revops/ev-bonus-last-error (fn [db _] (get-in db [:admin :ev-bonus-last-error])))

(defn bonus-total [rows]
  (reduce + 0 (keep #(->num (:bonus_amount %)) (or rows []))))

(defn average-achievement [rows]
  (let [values (->> (or rows []) (map :achievement_pct) (keep ->num))]
    (when (seq values)
      (/ (reduce + 0 values) (count values)))))

(defn- fmt-int [v]
  (when-let [n (->num v)]
    (.toLocaleString (js/Math.round n) "pt-BR")))

(defn- pct [v]
  (when-let [n (->num v)]
    (-> n (* 100) (.toFixed 0))))

(defn page []
  (let [filter-s (r/atom {:quarter 2 :year 2026})
        fetch!    (fn [{:keys [quarter year]}]
                    (rf/dispatch [:revops/fetch-ev-bonus quarter year]))
        change-filter! (fn [k v]
                         (let [next-filter (assoc @filter-s k v)]
                           (reset! filter-s next-filter)
                           (fetch! next-filter)))]
    (fetch! @filter-s)
    (fn []
      (let [items    @(rf/subscribe [:revops/ev-bonus])
            loading? @(rf/subscribe [:revops/ev-bonus-loading?])
            run-log  @(rf/subscribe [:revops/ev-bonus-run-log])
            last-err @(rf/subscribe [:revops/ev-bonus-last-error])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            rows     (or items [])
            total    (bonus-total rows)]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "vendas" "bônus EV"]
          :title "Bônus MRR Trimestral · EVs"
          :subtitle (str (count rows) " EVs apurados · Q" (:quarter @filter-s) "/" (:year @filter-s))
          :header-actions
          [[:button.btn.btn-secondary
            {:disabled loading?
             :on-click #(fetch! @filter-s)}
            [layout/icon "refresh" {:width 14 :height 14}] "Buscar"]
           [:button.btn.btn-primary
            {:disabled loading?
             :on-click #(rf/dispatch [:revops/run-ev-bonus (:quarter @filter-s) (:year @filter-s)])}
            [layout/icon "target" {:width 14 :height 14}] "Calcular bônus"]]}

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [q [1 2 3 4]]
            ^{:key q}
            [:button {:type "button"
                      :class (str "chip" (when (= q (:quarter @filter-s)) " active"))
                      :aria-pressed (str (= q (:quarter @filter-s)))
                      :on-click #(change-filter! :quarter q)}
             (str "Q" q)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y (available-years)]
            ^{:key y}
            [:button {:type "button"
                      :class (str "chip" (when (= y (:year @filter-s)) " active"))
                      :aria-pressed (str (= y (:year @filter-s)))
                      :on-click #(change-filter! :year y)}
             y])]

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs apurados"]
           [:div.kpi-value (str (count rows))]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "bônus total"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "·")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "atingimento médio"]
           [:div.kpi-value
            (let [avg (average-achievement rows)]
              [:<> (or (some-> avg (* 100) (.toFixed 0)) "·") [:span.frac "%"]])]]]

         (when (or run-log last-err)
           [:div.card {:style {:padding "16px 20px"}}
            [:div {:style {:display "flex"
                           :justify-content "space-between"
                           :align-items "baseline"
                           :gap "12px"
                           :margin-bottom "8px"}}
             [:h4 {:style {:margin 0}} "Log da última apuração"]
             (when run-log
               [:div.muted {:style {:font-family "var(--font-mono)"
                                     :font-size "11px"}}
                (str "Q" (:quarter run-log) "/" (:year run-log))])]
            (if last-err
              [:p.muted {:style {:margin 0}} last-err]
              [:ul {:style {:margin "0"
                            :padding-left "18px"
                            :color "var(--fg-2)"
                            :font-size "13px"
                            :line-height "1.6"}}
               (for [line (run-log-lines (:result run-log))]
                 ^{:key line}
                 [:li line])])])

         [:div.table-wrap
          [:table.table
           [:thead
            [:tr
             [:th "EV"]
             [:th.right "% Atingimento"]
             [:th.right "Salário Base"]
             [:th.right "Bônus"]
             [:th "Status"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 5 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? rows)
              [:tr [:td {:col-span 5 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhum dado · clique em Calcular para gerar a apuração"]]

              :else
              (for [r rows]
                ^{:key (or (:id r) (:ev_id r))}
                [:tr
                 [:td.name (or (:ev_name r) (str "EV " (:ev_id r)))]
                 [:td.right.num (str (or (pct (:achievement_pct r)) "·") "%")]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:salario_base_snapshot r)) "·"))]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:bonus_amount r)) "·"))]
                 [:td (if (:is_final r)
                        [:span.badge.badge-paid "Final"]
                        [:span.badge.badge-review "Rascunho"])]]))]]]]))))
