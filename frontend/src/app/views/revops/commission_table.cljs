(ns app.views.revops.commission-table
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Tabela de comissão (rates) — exibe somente as faixas configuradas no
;; backend. Cada linha vem de :revops/commission-table como
;; {:segment "..." :achievement_min "0" :achievement_max "100" :commission_pct "8.5"}.

(defn- pct-label [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (str (.toFixed n (if (or (= n (js/Math.floor n)) (>= n 100)) 0 1)) "%")))))

(defn- format-band-header [{:keys [achievement_min achievement_max]}]
  (let [hi (when achievement_max (js/parseFloat achievement_max))]
    (cond
      (nil? achievement_max)        (str achievement_min "%+")
      (and hi (>= hi 999))          (str achievement_min "%+")
      :else                         (str achievement_min "–" achievement_max "%"))))

(defn commission-table-page []
  (rf/dispatch [:revops/fetch-commission-table])
  (fn []
    (let [ct-data  @(rf/subscribe [:revops/commission-table])
          ct-meta  @(rf/subscribe [:revops/commission-table-meta])
          loading? @(rf/subscribe [:revops/commission-table-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          rows     (or ct-data [])
          ;; Group by segment, derive consistent band order.
          by-segment (group-by :segment rows)
          band-key   (juxt :achievement_min :achievement_max)
          all-bands  (->> rows
                          (map (fn [r] {:k (band-key r)
                                         :label (format-band-header r)}))
                          (distinct)
                          (sort-by :k))
          segments   (sort (keys by-segment))]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "configuração" "tabela %"]
        :title "Tabela de comissão"
        :subtitle (when (:version ct-meta)
                    (str "Versão v" (:version ct-meta) " · ativa"))
        :header-actions
        [[:button.btn.btn-primary
          {:on-click #(rf/dispatch [:revops/create-commission-version])}
          [layout/icon "plus" {:width 14 :height 14}] "Nova versão"]]}

       [:div.card
        [:div.card-head
         [:div [:h3 "Faixas de comissão"]
          [:div.card-sub "% sobre MRR por faixa de atingimento, dentro de cada segmento"]]]
        (cond
          (and loading? (empty? rows))
          [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
           "Carregando…"]

          (empty? rows)
          [:div.empty
           [:div.empty-illus [layout/icon "percent" {:width 40 :height 40}]]
           [:h4 "Nenhuma faixa configurada"]
           [:p "Crie uma nova versão da tabela de comissão para começar."]
           [:button.btn.btn-primary.btn-sm
            {:style {:margin-top "8px"}
             :on-click #(rf/dispatch [:revops/create-commission-version])}
            "Nova versão"]]

          :else
          [:table.matrix
           [:thead
            [:tr
             (into [[:th "Segmento"]]
                   (for [b all-bands]
                     ^{:key (:k b)} [:th (:label b)]))]]
           [:tbody
            (for [seg segments]
              ^{:key seg}
              [:tr
               [:td seg]
               (for [b all-bands
                     :let [row (->> (get by-segment seg)
                                    (filter #(= (band-key %) (:k b)))
                                    first)]]
                 ^{:key (:k b)}
                 [:td (or (pct-label (:commission_pct row)) "—")])])]])]])))
