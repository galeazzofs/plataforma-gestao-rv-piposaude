(ns app.views.revops.cn-quarterly-bonus
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(rf/reg-event-fx
 :revops/fetch-cn-quarterly-bonus
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (assoc-in db [:admin :cn-quarterly-bonus-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-quarterly-bonus
                            "?quarter=" quarter "&year=" year)
           :on-success [:revops/cn-quarterly-bonus-loaded]
           :on-failure [:revops/cn-quarterly-bonus-error]}}))

(rf/reg-event-db
 :revops/cn-quarterly-bonus-loaded
 (fn [db [_ resp]]
   (-> db
       (assoc-in [:admin :cn-quarterly-bonus] (:data resp))
       (assoc-in [:admin :cn-quarterly-bonus-loading?] false))))

(rf/reg-event-db
 :revops/cn-quarterly-bonus-error
 (fn [db _] (assoc-in db [:admin :cn-quarterly-bonus-loading?] false)))

(rf/reg-event-fx
 :revops/run-cn-quarterly-bonus
 (fn [_ [_ quarter year]]
   {:http {:method     :post
           :url        ep/cn-quarterly-bonus
           :body       {:quarter quarter :year year}
           :on-success [:revops/fetch-cn-quarterly-bonus quarter year]
           :on-failure [:revops/cn-quarterly-bonus-error]}}))

(rf/reg-event-fx
 :revops/finalize-cn-quarterly-bonus
 (fn [_ [_ quarter year]]
   {:http {:method     :post
           :url        ep/cn-quarterly-bonus-finalize
           :body       {:quarter quarter :year year}
           :on-success [:revops/fetch-cn-quarterly-bonus quarter year]
           :on-failure [:revops/cn-quarterly-bonus-error]}}))

(rf/reg-sub
 :revops/cn-quarterly-bonus
 (fn [db _] (get-in db [:admin :cn-quarterly-bonus] [])))

(rf/reg-sub
 :revops/cn-quarterly-bonus-loading?
 (fn [db _] (get-in db [:admin :cn-quarterly-bonus-loading?])))

(defn- fmt-int [v]
  (when v (.toLocaleString
            (js/Math.round (if (string? v) (js/parseFloat v) v))
            "pt-BR")))

(defn- pct [v]
  (when v (-> v js/parseFloat (* 100) (.toFixed 0))))

(defn- mult [v]
  (when v (-> v js/parseFloat (.toFixed 1))))

(defn page []
  (let [filter-s (r/atom {:quarter "2" :year "2026"})]
    (fn []
      (let [items    @(rf/subscribe [:revops/cn-quarterly-bonus])
            loading? @(rf/subscribe [:revops/cn-quarterly-bonus-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            rows     (or items [])
            total    (->> rows (map #(or (:bonus_amount %) 0))
                          (map #(if (string? %) (js/parseFloat %) %))
                          (reduce + 0))
            all-final? (and (seq rows) (every? :is_final rows))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "vendas" "bônus CN"]
          :title "Bônus CN Trimestral"
          :subtitle (str (count rows) " CNs apurados · Q"
                         (:quarter @filter-s) "/" (:year @filter-s))
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/fetch-cn-quarterly-bonus
                                      (:quarter @filter-s) (:year @filter-s)])}
            [layout/icon "refresh" {:width 14 :height 14}] "Buscar"]
           [:button.btn.btn-primary
            {:on-click #(rf/dispatch [:revops/run-cn-quarterly-bonus
                                      (:quarter @filter-s) (:year @filter-s)])}
            [layout/icon "target" {:width 14 :height 14}] "Calcular bônus"]
           [:button.btn.btn-primary
            {:disabled (or all-final? (empty? rows))
             :on-click #(rf/dispatch [:revops/finalize-cn-quarterly-bonus
                                      (:quarter @filter-s) (:year @filter-s)])}
            "Finalizar"]]}

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [q ["1" "2" "3" "4"]]
            ^{:key q}
            [:button {:type "button"
                      :class (str "chip" (when (= q (:quarter @filter-s)) " active"))
                      :aria-pressed (str (= q (:quarter @filter-s)))
                      :on-click #(swap! filter-s assoc :quarter q)}
             (str "Q" q)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px"
                         :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y ["2025" "2026"]]
            ^{:key y}
            [:button {:type "button"
                      :class (str "chip" (when (= y (:year @filter-s)) " active"))
                      :aria-pressed (str (= y (:year @filter-s)))
                      :on-click #(swap! filter-s assoc :year y)}
             y])]

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "CNs apurados"]
           [:div.kpi-value (str (count rows))]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "bônus total"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "·")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "atingimento médio"]
           [:div.kpi-value
            (let [vs (->> rows (map :pct_sao_trim) (filter some?)
                          (map #(if (string? %) (js/parseFloat %) %)))
                  avg (when (seq vs) (/ (reduce + 0 vs) (count vs)))]
              (str (or (some-> avg (* 100) (.toFixed 0)) "·")
                   [:span.frac "%"]))]]]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "CN"]
             [:th.right "SAO trim"]
             [:th.right "% atingimento"]
             [:th.right "Multiplicador"]
             [:th.right "Bônus"]
             [:th "Status"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 6
                         :style {:padding "32px" :text-align "center"
                                 :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? rows)
              [:tr [:td {:col-span 6
                         :style {:padding "48px" :text-align "center"
                                 :color "var(--fg-3)"}}
                    (str "Nenhum dado · clique em Calcular para gerar a apuração. "
                         "Lembre-se: os 3 meses do trimestre precisam estar finalizados.")]]

              :else
              (for [r rows]
                ^{:key (:id r)}
                [:tr
                 [:td.name (or (:cn_name r) (str "CN " (:cn_id r)))]
                 [:td.right.strong-num
                  (str (or (fmt-int (:sao_trim_realizado r)) "·") " / "
                       (or (fmt-int (:sao_trim_meta r)) "·"))]
                 [:td.right.num (str (or (pct (:pct_sao_trim r)) "·") "%")]
                 [:td.right.num (str (or (mult (:multiplicador r)) "·") "x")]
                 [:td.right.strong-num
                  (str "R$ " (or (fmt-int (:bonus_amount r)) "·"))]
                 [:td (if (:is_final r)
                        [:span.badge.badge-paid "Final"]
                        [:span.badge.badge-review "Rascunho"])]]))]]]]))))
