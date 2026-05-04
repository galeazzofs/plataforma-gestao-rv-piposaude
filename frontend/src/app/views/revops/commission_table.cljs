(ns app.views.revops.commission-table
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn- frac->pct
  "Convert fraction string to percentage number: \"0.07\" -> 7"
  [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (* n 100)))))

(defn- pct-label [v]
  (when-let [n (frac->pct v)]
    (str (.toFixed n (if (= n (js/Math.floor n)) 0 1)) "%")))

(defn- format-band-header [{:keys [achievement_min achievement_max]}]
  (let [lo (frac->pct achievement_min)
        hi (frac->pct achievement_max)]
    (cond
      (nil? hi)          (str (js/Math.round lo) "%+")
      (>= hi 500)        (str (js/Math.round lo) "%+")
      :else              (str (js/Math.round lo) "% a " (.toFixed hi 1) "%"))))

(defn- table-view [by-segment band-key all-bands segments]
  [:table.matrix
   [:thead
    (into [:tr [:th "Segmento"]]
          (for [b all-bands]
            ^{:key (str (:k b))}
            [:th (:label b)]))]
   [:tbody
    (for [seg segments]
      ^{:key seg}
      (into [:tr [:td seg]]
            (for [b all-bands
                  :let [row (->> (get by-segment seg)
                                 (filter #(= (band-key %) (:k b)))
                                 first)]]
              ^{:key (str (:k b))}
              [:td (or (pct-label (:commission_pct row)) "\u2014")])))]])

(defn commission-table-page []
  (rf/dispatch [:revops/fetch-commission-table])
  (fn []
    (let [ct-data  @(rf/subscribe [:revops/commission-table])
          ct-meta  @(rf/subscribe [:revops/commission-table-meta])
          loading? @(rf/subscribe [:revops/commission-table-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          rows     (or ct-data [])
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
        :crumbs ["plataforma rv" "configura\u00e7\u00e3o" "tabela %"]
        :title "Tabela de comiss\u00e3o"
        :subtitle (when (:version ct-meta)
                    (str "Vers\u00e3o v" (:version ct-meta) " \u00b7 ativa"))
        :header-actions
        [[:button.btn.btn-primary
          {:on-click #(rf/dispatch [:revops/create-commission-version])}
          [layout/icon "plus" {:width 14 :height 14}] "Nova vers\u00e3o"]]}

       [:div.card
        [:div.card-head
         [:div [:h3 "Faixas de comiss\u00e3o"]
          [:div.card-sub "% sobre MRR por faixa de atingimento, dentro de cada segmento"]]]
        (cond
          (and loading? (empty? rows))
          [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
           "Carregando\u2026"]

          (empty? rows)
          [:div.empty
           [:div.empty-illus [layout/icon "percent" {:width 40 :height 40}]]
           [:h4 "Nenhuma faixa configurada"]
           [:p "Crie uma nova vers\u00e3o da tabela de comiss\u00e3o para come\u00e7ar."]
           [:button.btn.btn-primary.btn-sm
            {:style {:margin-top "8px"}
             :on-click #(rf/dispatch [:revops/create-commission-version])}
            "Nova vers\u00e3o"]]

          :else
          [table-view by-segment band-key all-bands segments])]])))
