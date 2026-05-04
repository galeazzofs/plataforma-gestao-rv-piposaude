(ns app.views.revops.leadership-appraisal
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
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

(rf/reg-sub :revops/leadership-preview (fn [db _] (get-in db [:admin :leadership-preview] [])))
(rf/reg-sub :revops/leadership-appraisals (fn [db _] (get-in db [:admin :leadership-appraisals] [])))
(rf/reg-sub :revops/leadership-loading? (fn [db _] (get-in db [:admin :leadership-loading?])))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct [v]
  (when v (-> v js/parseFloat (* 100) (.toFixed 0))))

(defn- mult [v]
  (when v (-> v js/parseFloat (.toFixed 2)
              (clojure.string/replace "." ","))))

(defn page []
  (let [filter-s    (r/atom {:quarter "2" :year "2026"})
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
          :title "Apuração Liderança · Gerentes"
          :subtitle (str (count (or preview [])) " gerentes")
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
                             :inputs (mapv (fn [[gid vals]] (merge {:gerente_id gid} vals))
                                            @form-inputs)}]))}
            [layout/icon "target" {:width 14 :height 14}] "Calcular bônus"]]}

         [:div.filter-row
          (for [q ["1" "2" "3" "4"]]
            ^{:key q}
            [:div {:class (str "chip" (when (= q (:quarter @filter-s)) " active"))
                   :on-click #(swap! filter-s assoc :quarter q)}
             (str "Q" q)])
          [:div {:style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y ["2025" "2026"]]
            ^{:key y}
            [:div {:class (str "chip" (when (= y (:year @filter-s)) " active"))
                   :on-click #(swap! filter-s assoc :year y)}
             y])]

         (when (seq preview)
           [:div.card
            [:div.card-head
             [:div [:h3 "Inputs por gerente"]
              [:div.card-sub "Preencha os valores realizados antes de calcular"]]]
            [:div {:style {:display "flex" :flex-direction "column" :gap "12px"}}
             (for [{:keys [gerente_id gerente_name meta_mrr]} preview]
               ^{:key gerente_id}
               [:div {:style {:display "grid" :grid-template-columns "180px 200px 1fr 1fr 1fr"
                              :gap "12px" :align-items "end"
                              :padding "12px 0" :border-bottom "1px solid var(--border-subtle)"}}
                [:div
                 [:div.name gerente_name]
                 [:div.muted {:style {:font-family "var(--font-mono)" :font-size "11px"}}
                  (str "id " gerente_id)]]
                [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
                 (str "Meta MRR (auto): R$ " (or (fmt-int meta_mrr) "·"))]
                [inputs/input
                 {:label "MRR Realizado"
                  :value (get-in @form-inputs [gerente_id :realizado_mrr] "")
                  :on-change #(swap! form-inputs assoc-in [gerente_id :realizado_mrr] %)}]
                [inputs/input
                 {:label "Meta SQL" :type "number"
                  :value (get-in @form-inputs [gerente_id :meta_sql] "")
                  :on-change #(swap! form-inputs assoc-in [gerente_id :meta_sql] %)}]
                [inputs/input
                 {:label "SQL Realizado" :type "number"
                  :value (get-in @form-inputs [gerente_id :realizado_sql] "")
                  :on-change #(swap! form-inputs assoc-in [gerente_id :realizado_sql] %)}]])]])

         (cond
           (and loading? (empty? results))
           [:div.card [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}} "Carregando…"]]

           (seq results)
           [:div.card {:style {:padding 0}}
            [:div {:style {:padding "18px 20px 0"}}
             [:h3 "Resultados"]
             [:div.card-sub (str (count results) " gerentes apurados")]]
            [:table.table
             [:thead
              [:tr
               [:th "Gerente"]
               [:th.right "Meta MRR"]
               [:th.right "% MRR"]
               [:th.right "% SQL"]
               [:th.right "Mult."]
               [:th.right "Bônus"]
               [:th "Status"]]]
             [:tbody
              (for [row results]
                ^{:key (:id row)}
                [:tr
                 [:td.name (:gerente_name row)]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:meta_mrr row)) "·"))]
                 [:td.right.num (str (or (pct (:pct_mrr row)) "·") "%")]
                 [:td.right.num (str (or (pct (:pct_sql row)) "·") "%")]
                 [:td.right.num (str (or (mult (:multiplicador row)) "·") "x")]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:bonus_amount row)) "·"))]
                 [:td (if (:is_final row)
                        [:span.badge.badge-paid "Final"]
                        [:button.btn.btn-primary.btn-sm
                         {:on-click #(rf/dispatch [:revops/finalize-leadership
                                                    (:id row) (:quarter @filter-s) (:year @filter-s)])}
                         "Finalizar"])]])]]])]))))
