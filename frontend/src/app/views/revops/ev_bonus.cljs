(ns app.views.revops.ev-bonus
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.auth.subs]))

(rf/reg-event-fx
 :revops/fetch-ev-bonus
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (assoc-in db [:admin :ev-bonus-loading?] true)
    :http {:method     :get
           :url        (str ep/ev-bonus "?quarter=" quarter "&year=" year)
           :on-success [:revops/ev-bonus-loaded]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-event-db
 :revops/ev-bonus-loaded
 (fn [db [_ r]] (-> db (assoc-in [:admin :ev-bonus] (:data r))
                       (assoc-in [:admin :ev-bonus-loading?] false))))

(rf/reg-event-db :revops/ev-bonus-error (fn [db _] (assoc-in db [:admin :ev-bonus-loading?] false)))

(rf/reg-event-fx
 :revops/run-ev-bonus
 (fn [_ [_ quarter year]]
   {:http {:method     :post
           :url        ep/ev-bonus
           :body       {:quarter quarter :year year}
           :on-success [:revops/fetch-ev-bonus quarter year]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-sub :revops/ev-bonus (fn [db _] (get-in db [:admin :ev-bonus] [])))
(rf/reg-sub :revops/ev-bonus-loading? (fn [db _] (get-in db [:admin :ev-bonus-loading?])))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct [v]
  (when v (-> v js/parseFloat (* 100) (.toFixed 0))))

(defn page []
  (let [filter-s (r/atom {:quarter "2" :year "2026"})]
    (fn []
      (let [items    @(rf/subscribe [:revops/ev-bonus])
            loading? @(rf/subscribe [:revops/ev-bonus-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            total    (reduce + 0 (map #(or (:bonus_amount %) 0) (or items [])))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "vendas" "bônus EV"]
          :title "Bônus MRR Trimestral · EVs"
          :subtitle (str (count (or items [])) " EVs apurados · Q" (:quarter @filter-s) "/" (:year @filter-s))
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/fetch-ev-bonus (:quarter @filter-s) (:year @filter-s)])}
            [layout/icon "refresh" {:width 14 :height 14}] "Buscar"]
           [:button.btn.btn-primary
            {:on-click #(rf/dispatch [:revops/run-ev-bonus (:quarter @filter-s) (:year @filter-s)])}
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

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs apurados"]
           [:div.kpi-value (str (count (or items [])))]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "bônus total"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "—")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "atingimento médio"]
           [:div.kpi-value
            (let [vs (->> (or items []) (map :achievement_pct) (filter some?))
                  avg (when (seq vs) (/ (reduce + 0 vs) (count vs)))]
              (str (or (some-> avg (* 100) (.toFixed 0)) "—") [:span.frac "%"]))]]]

         [:div.card {:style {:padding 0}}
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

              (empty? items)
              [:tr [:td {:col-span 5 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhum dado · clique em Calcular para gerar a apuração"]]

              :else
              (for [r items]
                ^{:key (or (:id r) (:ev_id r))}
                [:tr
                 [:td.name (or (:ev_name r) (str "EV " (:ev_id r)))]
                 [:td.right.num (str (or (pct (:achievement_pct r)) "—") "%")]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:salario_base_snapshot r)) "—"))]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:bonus_amount r)) "—"))]
                 [:td (if (:is_final r)
                        [:span.badge.badge-paid "Final"]
                        [:span.badge.badge-review "Rascunho"])]]))]]]]))))
