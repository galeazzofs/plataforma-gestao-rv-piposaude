(ns app.views.cn.simulator
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; CN simulator — mirrors the design's split layout with parameters card
;; on the left and night-themed score card on the right, plus the curve.

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :cn/simulate
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/cn-simulate
           :body       payload
           :on-success [:cn/simulate-result]
           :on-failure [:cn/simulate-error]}}))

(rf/reg-event-db
 :cn/simulate-result
 (fn [db [_ response]]
   (assoc-in db [:cn :simulator :result] (:data response))))

(rf/reg-event-db
 :cn/simulate-error
 (fn [db _]
   (assoc-in db [:cn :simulator :result] nil)))

;; ── Subs ────────────────────────────────────────────────────────────────────

(rf/reg-sub
 :cn/simulator-result
 (fn [db _] (get-in db [:cn :simulator :result])))

;; ── Helpers ─────────────────────────────────────────────────────────────────

(defn- pct [v] (some-> v js/parseFloat (* 100) (.toFixed 0)))

(defn- mult [v]
  (when v (-> v js/parseFloat (.toFixed 2) (clojure.string/replace "." ","))))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- field [{:keys [label value placeholder help on-change]}]
  [:div.field
   [:label.field-label label]
   [:input.field-input
    {:value (or value "")
     :placeholder placeholder
     :on-change #(when on-change (on-change (.. % -target -value)))}]
   (when help [:span.field-help help])])

(defn- score-card [result]
  (let [pct-sao (pct (:pct_sao result))
        pct-vidas (pct (:pct_vidas result))
        pct-final (pct (:score_final result))
        mu (mult (:multiplicador result))
        comm (or (:commission_amount result) 62480)]
    [:div.score-card
     [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"
                    :position "relative" :z-index 1}}
      [:span {:style {:font-family "var(--font-mono)" :font-size "11px"
                      :color "rgba(255,255,255,.6)" :text-transform "uppercase"
                      :letter-spacing "0.06em"}}
       "resultado · simulação"]
      [:span.badge {:style {:background "rgba(59,154,255,.18)" :color "var(--cyan)"}}
       "live"]]
     [:div.score-row {:style {:position "relative" :z-index 1}}
      [:span "% SAO"]
      [:strong (str (or pct-sao "108") "%")]]
     [:div {:style {:height "1px" :background "rgba(255,255,255,.08)" :position "relative" :z-index 1}}]
     [:div.score-row {:style {:position "relative" :z-index 1}}
      [:span "% Vidas"]
      [:strong (str (or pct-vidas "91") "%")]]
     [:div {:style {:height "1px" :background "rgba(255,255,255,.08)" :position "relative" :z-index 1}}]
     [:div.score-row {:style {:position "relative" :z-index 1}}
      [:span "Score final"]
      [:strong (str (or pct-final "101") "%")]]
     [:div {:style {:height "1px" :background "rgba(255,255,255,.08)" :position "relative" :z-index 1}}]
     [:div.score-row {:style {:position "relative" :z-index 1}}
      [:span "Multiplicador"]
      [:strong {:style {:color "var(--cyan)"}}
       (or mu "1,15")
       [:span {:style {:font-family "var(--font-ui)" :font-size "14px"
                       :color "rgba(255,255,255,.6)"}}
        "x"]]]
     [:div.score-final {:style {:position "relative" :z-index 1}}
      [:span "Comissão estimada"]
      [:strong [:span.currency "R$"] (fmt-int comm)]]]))

(defn- multiplier-curve [score-pct]
  (let [s (or score-pct 101)
        x (+ 40 (* (/ (min s 130) 130) 560))
        ;; Map score to y on the step curve (clamp).
        y (cond (< s 60) 180  (< s 80) 140  (< s 100) 80  (< s 120) 50  :else 30)]
    [:svg.chart {:viewBox "0 0 600 200" :preserveAspectRatio "none"}
     [:g {:stroke "#E2E1DF" :stroke-width 1}
      [:line {:x1 40 :y1 20  :x2 600 :y2 20}]
      [:line {:x1 40 :y1 80  :x2 600 :y2 80}]
      [:line {:x1 40 :y1 140 :x2 600 :y2 140}]
      [:line {:x1 40 :y1 180 :x2 600 :y2 180}]]
     [:g {:font-family "IBM Plex Mono" :font-size 10 :fill "#BCBAB5"}
      [:text {:x 0 :y 24} "1.5x"]
      [:text {:x 0 :y 84} "1.0x"]
      [:text {:x 0 :y 144} "0.5x"]
      [:text {:x 0 :y 184} "0x"]]
     [:path {:d "M40 180 L180 180 L180 140 L300 140 L300 80 L420 80 L420 50 L600 50"
             :fill "none" :stroke "#000" :stroke-width 2.5 :stroke-linejoin "round"}]
     [:line {:x1 x :y1 20 :x2 x :y2 180 :stroke "#3B9AFF" :stroke-width 1 :stroke-dasharray "3 4"}]
     [:circle {:cx x :cy y :r 6 :fill "#3B9AFF" :stroke "#fff" :stroke-width 2}]
     [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
      [:text {:x 36 :y 198} "0%"]
      [:text {:x 170 :y 198} "60%"]
      [:text {:x 290 :y 198} "80%"]
      [:text {:x 410 :y 198} "100%"]
      [:text {:x 560 :y 198} "120%+"]]]))

(defn page []
  (let [form (r/atom {:sao_meta "500.000" :sao_realizado "540.000"
                      :vidas_meta "2.400" :vidas_realizado "2.180"})]
    (fn []
      (let [result @(rf/subscribe [:cn/simulator-result])
            user   @(rf/subscribe [:auth/current-user])
            route  @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "cn" "simulador"]
          :title "Simulador de comissão"
          :subtitle "Estime sua comissão variando metas e atingimento"
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(reset! form {:sao_meta "" :sao_realizado ""
                                      :vidas_meta "" :vidas_realizado ""})}
            "Resetar"]
           [:button.btn.btn-primary
            {:on-click #(rf/dispatch [:cn/simulate @form])}
            [layout/icon "target" {:width 14 :height 14}] "Simular"]]}

         ;; Two-col split: form / score
         [:div.sim-grid
          [:div.card
           [:div.card-head
            [:div [:h3 "Parâmetros"] [:div.card-sub "Informe metas e realizados do período"]]]
           [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
            [:div {:style {:display "grid" :grid-template-columns "1fr 1fr" :gap "12px"}}
             [field {:label "Meta SAO (R$)" :value (:sao_meta @form)
                     :help "soma anual de operações"
                     :on-change #(swap! form assoc :sao_meta %)}]
             [field {:label "SAO realizado (R$)" :value (:sao_realizado @form)
                     :help "vendas confirmadas"
                     :on-change #(swap! form assoc :sao_realizado %)}]]
            [:div {:style {:display "grid" :grid-template-columns "1fr 1fr" :gap "12px"}}
             [field {:label "Meta de vidas" :value (:vidas_meta @form)
                     :help "vidas vendidas"
                     :on-change #(swap! form assoc :vidas_meta %)}]
             [field {:label "Vidas realizadas" :value (:vidas_realizado @form)
                     :help "contabilizado no período"
                     :on-change #(swap! form assoc :vidas_realizado %)}]]
            [:div.callout {:style {:margin-top "8px"}}
             [layout/icon "info" {:width 20 :height 20}]
             [:div
              [:strong "Como o cálculo funciona"]
              [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
               "% SAO e % Vidas são ponderados (60/40) para gerar o score final, que mapeia o multiplicador na tabela de comissão."]]]]]

          [score-card result]]

         ;; Multiplier curve
         [:div.card
          [:div.card-head
           [:div [:h3 "Curva de multiplicador"] [:div.card-sub "Score final → multiplicador aplicado"]]
           [:div.legend
            [:span.legend-dot {:style {:color "var(--cyan)"}}
             (str "você (" (or (mult (:multiplicador result)) "1,15") "x)")]]]
          [multiplier-curve (some-> result :score_final js/parseFloat (* 100))]]

         ]))))
