(ns app.views.finance.saldo-devedor
  (:require [app.ds.cards :as cards]
            [app.ds.tokens :as t]))

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn saldo-by-year
  "Renders stat cards for saldo devedor per year.
   saldo-years: [{:year 2025 :amount 123456} ...]"
  [saldo-years]
  [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
   [:h3 {:style {:font-size (:lg t/font-sizes)
                 :font-weight (:semibold t/font-weights)
                 :margin "0 0 8px 0"}} "Saldo Devedor por Ano"]
   [:div {:style {:display "flex" :gap "16px" :flex-wrap "wrap"}}
    (for [{:keys [year amount]} (or saldo-years [])]
      ^{:key year}
      [cards/stat-card
       {:label    (str "Saldo " year)
        :value    (fmt-brl amount)
        :subtitle "Total em aberto"
        :color    :default}])]])
