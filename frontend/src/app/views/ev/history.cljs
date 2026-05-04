(ns app.views.ev.history
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- chart-quarters [items]
  (if (empty? items)
    [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                   :font-family "var(--font-mono)" :font-size "12px"}}
     "Sem ciclos para exibir"]
    (let [pts (vec items)
          n (count pts)
          slot (/ 540 n)
          max-v (or (->> pts (map :amount) (filter some?) (reduce max 1)) 1)
          scale (fn [v] (* (/ (or v 0) max-v) 180))]
      [:svg.chart {:viewBox "0 0 600 240" :preserveAspectRatio "none"}
       [:g {:stroke "#E2E1DF"}
        [:line {:x1 40 :y1 40 :x2 600 :y2 40}]
        [:line {:x1 40 :y1 100 :x2 600 :y2 100}]
        [:line {:x1 40 :y1 160 :x2 600 :y2 160}]
        [:line {:x1 40 :y1 220 :x2 600 :y2 220}]]
       (for [[i p] (map-indexed vector pts)
             :let [h (scale (:amount p))
                   x (+ 60 (* i slot))]]
         ^{:key i}
         [:rect {:x x :y (- 220 h) :width 44 :height h
                 :fill (if (:current? p) "#000" "#E6D9C2") :rx 2}])
       [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
        (for [[i p] (map-indexed vector pts)]
          ^{:key i}
          [:text {:x (+ 66 (* i slot)) :y 238} (:label p)])]])))

(defn history-page []
  (let [filters (r/atom {:quarter nil :year nil :status nil})]
    (rf/dispatch [:ev/fetch-policies @filters])
    (fn []
      (let [policies @(rf/subscribe [:ev/policies])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            ;; Group MRR by quarter/year for chart + summary table.
            by-period (->> (or policies [])
                           (group-by (fn [p] [(or (:cycle_year p) 2026)
                                              (or (:cycle_quarter p) 2)])))
            cycles (->> by-period
                        (map (fn [[[y q] rows]]
                               {:label (str "Q" q "/" y)
                                :year  y :quarter q
                                :deals (count rows)
                                :mrr   (reduce + 0 (map (fn [r] (or (:mrr_for_commission r) 0)) rows))
                                :commission (reduce + 0 (map (fn [r] (or (:commission_amount r) 0)) rows))
                                :achievement_pct (or (->> rows (map :achievement_pct) (filter some?) (reduce + 0) ((fn [s] (when (pos? (count rows)) (/ s (count rows))))))
                                                     0)
                                :status (or (some-> rows first :commission_status) "PROJECTED")}))
                        (sort-by (juxt :year :quarter) #(compare %2 %1)))
            total-recv  (reduce + 0 (map :commission cycles))
            avg-mrr     (when (seq cycles) (/ (reduce + 0 (map :mrr cycles)) (count cycles)))
            avg-pct     (when (seq cycles) (/ (reduce + 0 (map :achievement_pct cycles)) (count cycles)))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "ev" "histórico"]
          :title "Meu histórico"
          :subtitle (str (or (:name user) "EV") " · todos os ciclos")
          :header-actions nil}

         ;; KPIs (3-up) — only show numbers we actually have
         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label "total recebido"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total-recv) "0")]
           [:div.kpi-foot (str (count cycles) " ciclo" (when (not= 1 (count cycles)) "s"))]]
          [:div.kpi
           [:div.kpi-label "média trimestral (MRR)"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int avg-mrr) "·")]]
          [:div.kpi
           [:div.kpi-label "atingimento médio"]
           [:div.kpi-value (if avg-pct
                             [:<> (.toFixed avg-pct 0) [:span.frac "%"]]
                             "·")]]]

         ;; Chart
         [:div.card
          [:div.card-head
           [:div [:h3 "Evolução"] [:div.card-sub "Comissão recebida por trimestre"]]]
          [chart-quarters
           (->> cycles
                reverse
                (map-indexed (fn [i c] (assoc c :amount (:commission c)
                                               :current? (= i (dec (count cycles))))))
                vec)]]

         ;; Apurações table
         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "18px 20px 0"}}
           [:h3 "Apurações"]
           [:div.card-sub (str (count cycles) " ciclos")]]
          [:table.table
           [:thead
            [:tr
             [:th "Período"]
             [:th.center "Negócios"]
             [:th.right "MRR"]
             [:th "Atingimento"]
             [:th.right "Comissão"]
             [:th "Status"]]]
           [:tbody
            (if (empty? cycles)
              [:tr [:td {:col-span 6 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhum ciclo encontrado"]]
              (for [c cycles]
                ^{:key (:label c)}
                [:tr
                 [:td.name.num (:label c)]
                 [:td.center.num (str (:deals c))]
                 [:td.right.strong-num (str "R$ " (fmt-int (:mrr c)))]
                 [:td
                  [:div.cell-progress
                   [pct-bar (:achievement_pct c)
                    (cond (>= (:achievement_pct c) 100) "success"
                          (>= (:achievement_pct c) 70) "warn"
                          :else "danger")]
                   [:span.pct (str (.toFixed (or (:achievement_pct c) 0) 0) "%")]]]
                 [:td.right.strong-num (str "R$ " (fmt-int (:commission c)))]
                 [:td (case (:status c)
                        "SETTLED"   [:span.badge.badge-paid "Pago"]
                        "PROJECTED" [:span.badge.badge-review "Em revisão"]
                        "IN_PAYMENT"[:span.badge.badge-validating "Em pagamento"]
                        [:span.badge.badge-locked (or (:status c) "·")])]]))]]]]))))
