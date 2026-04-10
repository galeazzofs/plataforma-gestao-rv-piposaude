(ns app.views.cn.simulator
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]))

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

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub
 :cn/simulator-result
 (fn [db _] (get-in db [:cn :simulator :result])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn- result-panel [result]
  [:div {:style {:display "flex" :flex-direction "column" :gap "8px"
                 :padding "16px" :background t/surface-raised
                 :border-radius (:md t/border-radius)}}
   [:div {:style {:font-weight "600" :font-size "14px"}} "Resultado"]
   [:div (str "% SAO: " (* 100 (js/parseFloat (:pct_sao result))) "%")]
   [:div (str "% Vidas: " (* 100 (js/parseFloat (:pct_vidas result))) "%")]
   [:div (str "Score Final: " (* 100 (js/parseFloat (:score_final result))) "%")]
   [:div (str "Multiplicador: " (:multiplicador result) "x")]
   [:div {:style {:font-size "20px" :font-weight "700" :color t/color-primary}}
    (str "Comissão: R$ " (:commission_amount result))]])

(defn page []
  (let [form (r/atom {:sao_meta "" :sao_realizado "" :vidas_meta "" :vidas_realizado ""})]
    (fn []
      (let [result @(rf/subscribe [:cn/simulator-result])]
        [layout/page {:title "Simulador de Comissão"}
         [cards/card {:style {:max-width "480px"}}
          [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
           [inputs/text-field
            {:label "Meta SAO (R$)" :value (:sao_meta @form)
             :on-change #(swap! form assoc :sao_meta %)}]
           [inputs/text-field
            {:label "SAO Realizado (R$)" :value (:sao_realizado @form)
             :on-change #(swap! form assoc :sao_realizado %)}]
           [inputs/text-field
            {:label "Meta Vidas" :value (:vidas_meta @form)
             :on-change #(swap! form assoc :vidas_meta %)}]
           [inputs/text-field
            {:label "Vidas Realizadas" :value (:vidas_realizado @form)
             :on-change #(swap! form assoc :vidas_realizado %)}]
           [btn/button {:variant :primary
                        :on-click #(rf/dispatch [:cn/simulate @form])}
            "Simular"]
           (when result [result-panel result])]]]))))
