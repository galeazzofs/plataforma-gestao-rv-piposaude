(ns app.views.revops.leadership-appraisal
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.util.url :as url]
            [app.auth.subs]))

(rf/reg-event-fx
 :revops/fetch-leadership-preview
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (assoc-in db [:admin :leadership-loading?] true)
    :http {:method     :get
           :url        (str ep/leadership-preview "?quarter=" quarter "&year=" year)
           :on-success [:revops/leadership-preview-loaded]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-db
 :revops/leadership-preview-loaded
 (fn [db [_ r]] (-> db (assoc-in [:admin :leadership-preview] (:data r))
                       (assoc-in [:admin :leadership-loading?] false))))

(rf/reg-event-fx
 :revops/fetch-leadership-appraisals
 (fn [{:keys [db]} [_ quarter year]]
   {:http {:method     :get
           :url        (str ep/leadership-appraisal "?quarter=" quarter "&year=" year)
           :on-success [:revops/leadership-appraisals-loaded]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-db
 :revops/leadership-appraisals-loaded
 (fn [db [_ r]] (assoc-in db [:admin :leadership-appraisals] (:data r))))

(rf/reg-event-db :revops/leadership-error (fn [db _] (assoc-in db [:admin :leadership-loading?] false)))

(rf/reg-event-fx
 :revops/run-leadership-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/leadership-appraisal
           :body       payload
           :on-success [:revops/fetch-leadership-appraisals
                        (:quarter payload) (:year payload)]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-fx
 :revops/finalize-leadership
 (fn [_ [_ id quarter year]]
   {:http {:method     :post
           :url        (ep/leadership-finalize id)
           :body       {}
           :on-success [:revops/fetch-leadership-appraisals quarter year]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-fx
 :revops/transition-leadership
 (fn [_ [_ id to-status quarter year]]
   {:http {:method     :post
           :url        (str ep/leadership-appraisal "/" id "/transition")
           :body       {:to to-status}
           :on-success [:revops/fetch-leadership-appraisals quarter year]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-sub :revops/leadership-preview (fn [db _] (get-in db [:admin :leadership-preview] [])))
(rf/reg-sub :revops/leadership-appraisals (fn [db _] (get-in db [:admin :leadership-appraisals] [])))
(rf/reg-sub :revops/leadership-loading? (fn [db _] (get-in db [:admin :leadership-loading?])))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct [v]
  (when v (-> v js/parseFloat (* 100) (.toFixed 0))))

(defn- mult [v]
  (when v (-> v js/parseFloat (.toFixed 2)
              (str/replace "." ","))))

(defn- status->badge [status]
  (case status
    "DRAFT"         [:span.badge.badge-draft "Draft"]
    "CALCULATING"   [:span.badge.badge-calc "Calculating"]
    "VALIDATING"    [:span.badge.badge-validating "Validating"]
    "LIDER_REVIEW"  [:span.badge.badge-review "Líder Review"]
    "REVOPS_REVIEW" [:span.badge.badge-review "RevOps Review"]
    "LOCKED"        [:span.badge.badge-paid "Locked"]
    [:span.badge.badge-locked (or status "·")]))

(defn- next-status-action [status]
  (case status
    "DRAFT"          ["Iniciar"        "CALCULATING"]
    "CALCULATING"    ["Liberar p/ Líder" "VALIDATING"]
    "VALIDATING"     ["Avançar"        "LIDER_REVIEW"]
    "LIDER_REVIEW"   ["Aprovar (Líder)" "REVOPS_REVIEW"]
    "REVOPS_REVIEW"  ["Fechar"         "LOCKED"]
    nil))

(defn page []
  (let [filter-s    (r/atom {:quarter (or (url/query-param "quarter") "2")
                             :year    (or (url/query-param "year") "2026")})
        form-inputs (r/atom {})]
    (fn []
      (let [preview  @(rf/subscribe [:revops/leadership-preview])
            results  @(rf/subscribe [:revops/leadership-appraisals])
            loading? @(rf/subscribe [:revops/leadership-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "gestão de time" "apuração liderança"]
          :title "Apuração Liderança · Líderes de Vendas"
          :subtitle (str (count (or preview [])) " líderes")
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/fetch-leadership-preview
                                      (:quarter @filter-s) (:year @filter-s)])}
            [layout/icon "refresh" {:width 14 :height 14}] "Carregar"]
           [:button.btn.btn-primary
            {:disabled (empty? preview)
             :on-click (fn []
                         (rf/dispatch
                           [:revops/run-leadership-appraisal
                            {:quarter (:quarter @filter-s)
                             :year (:year @filter-s)
                             :inputs (mapv (fn [[gid vals]] (merge {:lider_vendas_id gid} vals))
                                            @form-inputs)}]))}
            [layout/icon "target" {:width 14 :height 14}] "Calcular bônus"]]}

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [q ["1" "2" "3" "4"]]
            ^{:key q}
            [:button {:type "button"
                      :class (str "chip" (when (= q (:quarter @filter-s)) " active"))
                      :aria-pressed (str (= q (:quarter @filter-s)))
                      :on-click #(swap! filter-s assoc :quarter q)}
             (str "Q" q)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y ["2025" "2026"]]
            ^{:key y}
            [:button {:type "button"
                      :class (str "chip" (when (= y (:year @filter-s)) " active"))
                      :aria-pressed (str (= y (:year @filter-s)))
                      :on-click #(swap! filter-s assoc :year y)}
             y])]

         (when (seq preview)
           [:div.card
            [:div.card-head
             [:div [:h3 "Inputs por líder"]
              [:div.card-sub
               "MRR Realizado vem auto-preenchido com a soma do "
               [:code "total_mrr"]
               " dos EVs do time. Edite se precisar corrigir."]]]
            [:div {:style {:display "flex" :flex-direction "column" :gap "12px"}}
             (for [{:keys [lider_vendas_id lider_vendas_name
                           meta_mrr realizado_mrr_auto]} preview]
               ^{:key lider_vendas_id}
               [:div.appraisal-row
                [:div
                 [:div.name lider_vendas_name]
                 [:div.muted {:style {:font-family "var(--font-mono)" :font-size "11px"}}
                  (str "id " lider_vendas_id)]]
                [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
                 (str "Meta MRR (auto): R$ " (or (fmt-int meta_mrr) "·"))]
                [inputs/input
                 {:label "MRR Realizado (auto)"
                  :placeholder (str "R$ " (or (fmt-int realizado_mrr_auto) "·"))
                  :value (get-in @form-inputs [lider_vendas_id :realizado_mrr]
                                 (or realizado_mrr_auto ""))
                  :on-change #(swap! form-inputs assoc-in [lider_vendas_id :realizado_mrr] %)}]
                [inputs/input
                 {:label "Meta SQL" :type "number"
                  :value (get-in @form-inputs [lider_vendas_id :meta_sql] "")
                  :on-change #(swap! form-inputs assoc-in [lider_vendas_id :meta_sql] %)}]
                [inputs/input
                 {:label "SQL Realizado" :type "number"
                  :value (get-in @form-inputs [lider_vendas_id :realizado_sql] "")
                  :on-change #(swap! form-inputs assoc-in [lider_vendas_id :realizado_sql] %)}]])]])

         (cond
           (and loading? (empty? results))
           [:div.card [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}} "Carregando…"]]

           (seq results)
           [:div.card {:style {:padding 0}}
            [:div {:style {:padding "18px 20px 0"}}
             [:h3 "Resultados"]
             [:div.card-sub (str (count results) " líderes apurados")]]
            [:table.table
             [:thead
              [:tr
               [:th "Líder de Vendas"]
               [:th.right "Meta MRR"]
               [:th.right "% MRR"]
               [:th.right "% SQL"]
               [:th.right "Mult."]
               [:th.right "Bônus"]
               [:th "Status"]
               [:th.right "Ação"]]]
             [:tbody
              (for [row results]
                ^{:key (:id row)}
                (let [next-action (next-status-action (:status row))]
                  [:tr
                   [:td.name (:lider_vendas_name row)]
                   [:td.right.strong-num (str "R$ " (or (fmt-int (:meta_mrr row)) "·"))]
                   [:td.right.num (str (or (pct (:pct_mrr row)) "·") "%")]
                   [:td.right.num (str (or (pct (:pct_sql row)) "·") "%")]
                   [:td.right.num (str (or (mult (:multiplicador row)) "·") "x")]
                   [:td.right.strong-num (str "R$ " (or (fmt-int (:bonus_amount row)) "·"))]
                   [:td [status->badge (:status row)]]
                   [:td.right
                    (cond
                      (:is_final row)
                      [:span.muted {:style {:font-family "var(--font-mono)"
                                            :font-size "11px"}}
                       "fechado"]

                      next-action
                      [:button.btn.btn-primary.btn-sm
                       {:on-click #(rf/dispatch
                                    [:revops/transition-leadership
                                     (:id row) (second next-action)
                                     (:quarter @filter-s) (:year @filter-s)])}
                       (first next-action)]

                      :else nil)]]))]]])]))))
